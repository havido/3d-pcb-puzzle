-- ui.lua: every widget of Goose Doctor. Owner: @talfee.
-- Each screen is one of her full-screen 16-colour images (app/goose/art/*.png
-- -> img/*.bin, see UI_NOTES.md), drawn portrait and rotated clockwise into
-- the 320x240 framebuffer because the goose plate holds the badge rotated a
-- quarter turn. LVGL labels can't rotate, so every bit of text this file
-- draws on top of the art is either:
--   - the countdown: built from `badge.ui.box` rectangles as a rotated
--     seven-segment display (see the "Countdown" section below), because
--     its value changes at runtime and can't be pre-rendered, or
--   - a fixed string: pre-rendered rotated by app/tools/make_text_art.py
--     into a small `.bin` and shown with a plain `badge.ui.image`.
-- A red flash covers the screen on a PENALTY touch. One image widget is
-- reused via set_src for the four screens, so only one screen's art is
-- decoded at a time.
--
-- Keep these functions, names and arguments (game.lua calls them, and
-- `lua app/tools/test.lua` checks them):
--
--   M.init(root)
--       Build every widget once. root is the app screen; only use it as a
--       parent. Called once from on_enter.
--   M.show(screen, info)
--       Show one screen and hide the others.
--       screen: "start" | "operating" | "success" | "failure"
--       info (always a table):
--         time_left_ms  integer >= 0    countdown remaining
--         stage         "goal1" | "goal2"   which target is next
--         best_ms       integer or nil  fastest win so far, nil = none yet
--       Called on every screen change, and again when the stage changes
--       (same screen "operating", new stage).
--   M.set_time(ms)
--       Countdown changed, ms >= 0. Called every 100 ms while operating, and
--       immediately after a PENALTY touch (the time jumps down).
--   M.touch(zone)
--       The tweezers hit the goose outline. zone is always 1 (single PENALTY
--       net). Play the flinch/flash here.
--   M.tick(now_ms)
--       Called every ~20 ms with badge.sys.ms(). Advance animations here.
--       Must return in a few ms: no loops that wait, no big redraws.
--
-- Buttons are game.lua's job, so never read them here. Only SW6 (reported as
-- A, B or AUX1 -- unconfirmed) and HOME reach the player through the plate,
-- so there is no quit button to draw. Don't create widgets outside init.
--
-- best_ms (success screen) is intentionally not drawn: the only free
-- background on the success art is a narrow strip running the wrong way (it
-- reads as a tall column to the player, not a left-to-right line -- see
-- UI_NOTES.md "Rotated art"), so a second seven-segment readout would either
-- be cramped or stacked vertically. Not worth the widget count for a
-- stretch feature; `info.best_ms` is still accepted per the contract.

local M = {}

local ART = {                      -- screen -> image file, pushed from img/
  start = "start.bin",
  operating = "operating.bin",
  success = "success.bin",
  failure = "failure.bin",
}

local PANEL = 0xf2f2f2            -- colour of the drawn LCD timer panel
local INK = 0x111111
local RED = 0xff5757
local FLASH_MS = 250              -- how long the red "touch" overlay stays up

-- Where the operating art draws the LCD timer panel, measured on the
-- rotated 320x240 render (app/CLAUDE.md's "badge rotated a quarter turn"):
-- it is a *portrait* panel on screen (tall and narrow) that reads as a wide
-- panel to the player looking at the mounted plate.
local TIMER_X, TIMER_Y, TIMER_W, TIMER_H = 149, 26, 82, 192

-- Where the operating art leaves free background for the stage cue image
-- (a fully empty column to the right of the panel and the art's own
-- decorative "Operating..." wordmark -- see UI_NOTES.md for how this was
-- found). It is tall and narrow on screen, same as the timer panel, because
-- that is what reads as a normal left-to-right line of text to the player.
local STAGE_X, STAGE_Y = 280, 4

------------------------------------------------------------------------
-- Countdown: a rotated seven-segment display built out of boxes.
--
-- Each digit is designed in "local" space the way a player would draw it
-- upright: u = left-right, v = top-down, v=0 at the top. That local box is
-- then rotated 90 deg clockwise into framebuffer space -- the same turn
-- `badge.py img --rotate cw` gives the screen art -- with:
--   fb_x = X0 + (SEG_H - v)      fb_y = Y0 + u
-- so local "up" (v decreasing) becomes fb_x increasing (screen-right), and
-- local "right" (u increasing) becomes fb_y increasing (screen-down). A
-- digit that is tall in local space (SEG_H) ends up occupying the panel's
-- narrow fb_x width; four digits and a colon laid out along increasing u
-- end up laid out along the panel's long fb_y axis, reading left-to-right
-- to the player. All coordinates below are relative to timer_box, which is
-- itself positioned at (TIMER_X, TIMER_Y) in screen space.
------------------------------------------------------------------------

local SEG_T = 6                  -- segment thickness, local units
local SEG_W, SEG_H = 32, 54      -- one digit's local width x height
local COLON_W = 10                -- colon's local width (shares SEG_H)
local GAP = 6                     -- gap between consecutive elements

-- Segment rectangles in local {u0, v0, u1, v1}, a classic 7-seg layout.
-- (`//` not `/`: coordinates must be actual Lua integers, not 27.0 floats.)
local SEG_RECT = {
  a = { SEG_T, 0,               SEG_W - SEG_T, SEG_T },               -- top
  b = { SEG_W - SEG_T, SEG_T,   SEG_W,          SEG_H // 2 },         -- upper right
  c = { SEG_W - SEG_T, SEG_H // 2, SEG_W,       SEG_H - SEG_T },      -- lower right
  d = { SEG_T, SEG_H - SEG_T,   SEG_W - SEG_T, SEG_H },                -- bottom
  e = { 0,      SEG_H // 2,     SEG_T,          SEG_H - SEG_T },      -- lower left
  f = { 0,      SEG_T,          SEG_T,          SEG_H // 2 },         -- upper left
  g = { SEG_T, SEG_H // 2 - SEG_T // 2, SEG_W - SEG_T, SEG_H // 2 + SEG_T // 2 }, -- middle
}
local SEG_LETTERS = { "a", "b", "c", "d", "e", "f", "g" }

-- Which segments are lit for each digit 0-9, in SEG_LETTERS order.
local DIGIT_PATTERN = {
  [0] = { 1, 1, 1, 1, 1, 1, 0 },
  [1] = { 0, 1, 1, 0, 0, 0, 0 },
  [2] = { 1, 1, 0, 1, 1, 0, 1 },
  [3] = { 1, 1, 1, 1, 0, 0, 1 },
  [4] = { 0, 1, 1, 0, 0, 1, 1 },
  [5] = { 1, 0, 1, 1, 0, 1, 1 },
  [6] = { 1, 0, 1, 1, 1, 1, 1 },
  [7] = { 1, 1, 1, 0, 0, 0, 0 },
  [8] = { 1, 1, 1, 1, 1, 1, 1 },
  [9] = { 1, 1, 1, 1, 0, 1, 1 },
}
local ZERO_PATTERN = { 0, 0, 0, 0, 0, 0, 0 }

-- Colon dots, local {u0, v0, u1, v1}, sharing SEG_H with the digits (54):
-- two 8x8 squares symmetric about the mid-height (27), like a real LCD colon.
local COLON_RECT = {
  { 1, 14, 9, 22 },
  { 1, 32, 9, 40 },
}

-- fb_x/fb_y margin (relative to timer_box) that centres the digit block in
-- the panel's short axis, and the y0 (relative to timer_box) of each of the
-- five elements (digit, digit, colon, digit, digit) along its long axis.
local PANEL_MARGIN_X = math.floor((TIMER_W - SEG_H) / 2)
local ELEMENT_Y = {}
do
  local total = 4 * SEG_W + COLON_W + 4 * GAP
  local y = math.floor((TIMER_H - total) / 2)
  ELEMENT_Y[1] = y; y = y + SEG_W + GAP        -- MM tens
  ELEMENT_Y[2] = y; y = y + SEG_W + GAP        -- MM ones
  ELEMENT_Y.colon = y; y = y + COLON_W + GAP
  ELEMENT_Y[3] = y; y = y + SEG_W + GAP        -- SS tens
  ELEMENT_Y[4] = y                             -- SS ones
end

-- Map one local rect at element origin y0 to a (x, y, w, h) box relative to
-- timer_box.
local function local_to_fb(y0, rect)
  local u0, v0, u1, v1 = rect[1], rect[2], rect[3], rect[4]
  local x = PANEL_MARGIN_X + (SEG_H - v1)
  local w = v1 - v0
  local y = y0 + u0
  local h = u1 - u0
  return x, y, w, h
end

local art, timer_box, stage_img
local flash_box, flash_img
local flash_until = 0

local digit_box = {}     -- digit_box[digit_index][letter] = box widget
local digit_value = {}   -- last value shown per digit, or nil

local function make_digit(y0)
  local segs = {}
  for _, letter in ipairs(SEG_LETTERS) do
    local x, y, w, h = local_to_fb(y0, SEG_RECT[letter])
    local b = badge.ui.box(timer_box, w, h)
    b:set_pos(x, y)
    b:style({ bg_color = INK, radius = 0, border_width = 0, pad_all = 0 })
    b:hidden(true)
    segs[letter] = b
  end
  return segs
end

local function set_digit(i, value)
  if digit_value[i] == value then return end
  local old = DIGIT_PATTERN[digit_value[i]] or ZERO_PATTERN
  local new = DIGIT_PATTERN[value] or ZERO_PATTERN
  for j, letter in ipairs(SEG_LETTERS) do
    if old[j] ~= new[j] then
      digit_box[i][letter]:hidden(new[j] == 0)
    end
  end
  digit_value[i] = value
end

local function fmt_digits(ms)
  local total_s = math.floor(math.max(0, ms) / 1000)
  local mm = math.floor(total_s / 60)
  local ss = total_s % 60
  return math.floor(mm / 10) % 10, mm % 10, math.floor(ss / 10) % 10, ss % 10
end

------------------------------------------------------------------------

function M.init(root)
  art = badge.ui.image(root, ART.start)
  art:set_pos(0, 0)

  -- Live countdown, drawn over the art's static "00:00" placeholder.
  timer_box = badge.ui.box(root, TIMER_W, TIMER_H)
  timer_box:set_pos(TIMER_X, TIMER_Y)
  timer_box:style({ bg_color = PANEL, radius = 0, border_width = 0, pad_all = 0 })

  for i = 1, 4 do
    digit_box[i] = make_digit(ELEMENT_Y[i])
  end
  for _, rect in ipairs(COLON_RECT) do
    local x, y, w, h = local_to_fb(ELEMENT_Y.colon, rect)
    local b = badge.ui.box(timer_box, w, h)
    b:set_pos(x, y)
    b:style({ bg_color = INK, radius = 0, border_width = 0, pad_all = 0 })
  end

  -- Stage cue: a fixed string per stage, pre-rotated at build time (see
  -- app/tools/make_text_art.py) because a live label can't rotate.
  stage_img = badge.ui.image(root, "stage_goal1.bin")
  stage_img:set_pos(STAGE_X, STAGE_Y)

  flash_box = badge.ui.box(root, 320, 240)
  flash_box:set_pos(0, 0)
  flash_box:style({ bg_color = RED, bg_opa = 140, radius = 0, border_width = 0 })
  flash_img = badge.ui.image(flash_box, "ouch.bin")
  flash_img:align("center", 0, 0)
  flash_box:hidden(true)
end

function M.show(name, info)
  info = info or {}
  art:set_src(ART[name] or ART.start)

  local playing = name == "operating"
  timer_box:hidden(not playing)
  stage_img:hidden(not playing)
  if playing then
    M.set_time(info.time_left_ms or 0)
    stage_img:set_src(info.stage == "goal2" and "stage_goal2.bin" or "stage_goal1.bin")
  end

  -- info.best_ms (success screen) has no on-screen readout -- see the file
  -- header comment for why.
end

function M.set_time(ms)
  local d1, d2, d3, d4 = fmt_digits(ms)
  set_digit(1, d1); set_digit(2, d2); set_digit(3, d3); set_digit(4, d4)
end

function M.touch(zone)
  flash_box:hidden(false)
  flash_box:bring_to_front()
  flash_until = badge.sys.ms() + FLASH_MS
end

function M.tick(now)
  if flash_until > 0 and now >= flash_until then
    flash_until = 0
    flash_box:hidden(true)
  end
end

return M

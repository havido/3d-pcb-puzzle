-- ui.lua: every widget of Goose Doctor. Owner: @talfee.
-- Each screen is one of her full-screen 16-colour images (app/goose/art/*.png
-- -> img/*.bin, see UI_NOTES.md), with live text drawn on top: the countdown
-- sits in the drawn timer panel, the stage cue and best time are labels, and
-- a red flash covers the screen on a PENALTY touch. One image widget is
-- reused via set_src, so only one screen's art is decoded at a time.
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

local M = {}

local ART = {                      -- screen -> image file, pushed from img/
  start = "start.bin",
  operating = "operating.bin",
  success = "success.bin",
  failure = "failure.bin",
}

local PANEL = 0xf2f2f2            -- colour of the drawn timer panel
local INK = 0x111111
local RED = 0xff5757
local FLASH_MS = 250              -- how long the red "touch" overlay stays up

-- Where her art draws the LCD timer panel (measured on the 320x240 render).
local TIMER_X, TIMER_Y, TIMER_W, TIMER_H = 58, 60, 230, 58

local art, timer_box, timer_label, stage_label, best_label
local flash_box, flash_label
local flash_until = 0

local function label(parent, text, size, color)
  local l = badge.ui.label(parent, text)
  l:style({ text_color = color or INK, text_font = size or 16 })
  return l
end

local function fmt_time(ms)
  ms = math.max(0, math.floor(ms))
  local cs = math.floor(ms / 10) % 100
  local s = math.floor(ms / 1000) % 60
  local m = math.floor(ms / 60000)
  return string.format("%02d:%02d:%02d", m, s, cs)
end

function M.init(root)
  art = badge.ui.image(root, ART.start)
  art:set_pos(0, 0)

  -- Live countdown, drawn over the art's static "00:00:00".
  timer_box = badge.ui.box(root, TIMER_W, TIMER_H)
  timer_box:set_pos(TIMER_X, TIMER_Y)
  timer_box:style({ bg_color = PANEL, radius = 0, border_width = 0, pad_all = 0 })
  timer_label = label(timer_box, "00:00:00", 24)
  timer_label:align("center", 0, 0)

  stage_label = label(root, "", 18)
  stage_label:align("bottom_mid", 0, -8)

  best_label = label(root, "", 16)
  best_label:set_pos(8, 8)

  flash_box = badge.ui.box(root, 320, 240)
  flash_box:set_pos(0, 0)
  flash_box:style({ bg_color = RED, bg_opa = 140, radius = 0, border_width = 0 })
  flash_label = label(flash_box, "OUCH!", 24, 0xffffff)
  flash_label:align("center", 0, 0)
  flash_box:hidden(true)
end

function M.show(name, info)
  info = info or {}
  art:set_src(ART[name] or ART.start)

  local playing = name == "operating"
  timer_box:hidden(not playing)
  stage_label:hidden(not playing)
  if playing then
    M.set_time(info.time_left_ms or 0)
    stage_label:set_text(info.stage == "goal2" and "Now the BELLY loop"
                         or "Reach the TAIL loop")
  end

  local won = name == "success"
  best_label:hidden(not won)
  if won then
    best_label:set_text(info.best_ms and ("Best " .. fmt_time(info.best_ms)) or "")
  end
end

function M.set_time(ms)
  timer_label:set_text(fmt_time(ms))
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

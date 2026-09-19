-- ui.lua: every widget of Goose Doctor. Owner: @talfee.
-- This is a STUB with plain widgets in the Canva colours (assets/*.png).
-- Replace it freely, but keep the functions below with these exact names and
-- arguments: game.lua calls them, and `lua app/tools/test.lua` checks them.
--
--   M.init(root)
--       Build every widget once. root is the app screen; only use it as a
--       parent. Called once from on_enter.
--   M.show(screen, info)
--       Show one full screen and hide the others.
--       screen: "start" | "operating" | "success" | "failure"
--       info (always a table):
--         time_left_ms  integer >= 0    countdown remaining
--         stage         "goal1" | "goal2"   which goal is next: goal1 (the
--                       tail loop) first, then goal2 (the belly loop)
--         best_ms       integer or nil  fastest win so far, nil = none yet
--       Called on every screen change, and again when the stage changes
--       (same screen "operating", new stage).
--   M.set_time(ms)
--       Countdown changed, ms >= 0. Called every 100 ms while operating, and
--       immediately after a penalty touch (the time jumps down).
--   M.touch(zone)
--       The tweezers hit the PENALTY net. zone is always 1 (one penalty
--       net on this board). Play the flinch/flash here. Called at most once
--       per half second.
--   M.tick(now_ms)
--       Called every ~20 ms with badge.sys.ms(). Advance animations here.
--       Must return in a few ms: no loops that wait, no big redraws.
--
-- Buttons are game.lua's job, so never read them here: only the exposed SW6
-- button starts/retries (its exact badge.input.BUTTON constant isn't known
-- yet -- game.lua accepts any of A, B or AUX1), and HOME always exits
-- (default firmware behaviour, intercepted before it reaches the app).
-- Show a generic "press to start/retry" hint, not a specific button name,
-- and no "quit" hint -- HOME is the only way out and it isn't a game button.
-- Don't create widgets outside init. The "preview" app (badge.py push
-- preview) drives all of this by hand.

local M = {}

local YELLOW = 0xfce884   -- start + operating background
local GREEN = 0xb9fc84    -- success background
local RED = 0xff5757      -- failure background
local PANEL = 0xf2f2f2    -- white-ish boxes with a black border
local INK = 0x111111      -- text on light backgrounds
local FLASH_MS = 250      -- how long the red "touch" overlay stays up

local screens = {}        -- name -> full-screen box
local timer_label, stage_label, best_label
local flash_box, flash_label
local flash_until = 0

local function panel(parent, w, h)
  local b = badge.ui.box(parent, w, h)
  b:style({ bg_color = PANEL, border_color = INK, border_width = 2,
            radius = 8, pad_all = 0 })
  return b
end

local function text(parent, s, size)
  local l = badge.ui.label(parent, s)
  l:style({ text_color = INK, text_font = size or 16 })
  return l
end

local function screen(root, name, color)
  local s = badge.ui.box(root, 320, 240)
  s:set_pos(0, 0)
  s:style({ bg_color = color, radius = 0, border_width = 0, pad_all = 0 })
  s:hidden(true)
  screens[name] = s
  return s
end

-- "Press to Start/Retry" + "HOME exits" hint in the bottom-right corner.
local function buttons_hint(parent, verb)
  local p = panel(parent, 96, 52)
  p:align("bottom_right", -10, -10)
  local l = text(p, "Press to\n" .. verb .. "\nHOME exits", 14)
  l:align("center", 0, 0)
end

local function fmt_time(ms)
  ms = math.max(0, math.floor(ms))
  local cs = math.floor(ms / 10) % 100
  local s = math.floor(ms / 1000) % 60
  local m = math.floor(ms / 60000)
  return string.format("%02d:%02d:%02d", m, s, cs)
end

function M.init(root)
  -- start
  local s = screen(root, "start", YELLOW)
  local l = text(s, "welcome to", 20)
  l:align("top_mid", 0, 30)
  l = text(s, "Goose Doctor", 24)
  l:align("top_mid", 0, 62)
  buttons_hint(s, "Start")

  -- operating
  s = screen(root, "operating", YELLOW)
  l = text(s, "Operating...", 20)
  l:align("top_mid", 0, 16)
  local t = panel(s, 220, 64)
  t:align("top_mid", 0, 50)
  timer_label = text(t, "00:00:00", 24)
  timer_label:align("center", 0, 0)
  stage_label = text(s, "", 18)
  stage_label:align("top_mid", 0, 126)

  -- success
  s = screen(root, "success", GREEN)
  local sign = panel(s, 160, 56)
  sign:align("bottom_left", 10, -10)
  l = text(sign, "SUCCESS!", 24)
  l:align("center", 0, 0)
  best_label = text(s, "", 18)
  best_label:align("top_left", 12, 12)
  buttons_hint(s, "Retry")

  -- failure
  s = screen(root, "failure", RED)
  sign = panel(s, 160, 56)
  sign:align("top_left", 10, 20)
  l = text(sign, "FAILURE!", 24)
  l:align("center", 0, 0)
  buttons_hint(s, "Retry")

  -- touch flash, drawn over everything
  flash_box = badge.ui.box(root, 320, 240)
  flash_box:set_pos(0, 0)
  flash_box:style({ bg_color = RED, bg_opa = 140, radius = 0, border_width = 0 })
  flash_label = text(flash_box, "", 24)
  flash_label:align("center", 0, 0)
  flash_box:hidden(true)
end

function M.show(name, info)
  for n, s in pairs(screens) do s:hidden(n ~= name) end
  info = info or {}
  if name == "operating" then
    M.set_time(info.time_left_ms or 0)
    stage_label:set_text(info.stage == "goal2" and "Now the BELLY loop"
                         or "Reach the TAIL loop")
  elseif name == "success" then
    best_label:set_text(info.best_ms and ("Best " .. fmt_time(info.best_ms)) or "")
  end
end

function M.set_time(ms)
  timer_label:set_text(fmt_time(ms))
end

function M.touch(zone)
  flash_label:set_text("OUCH!")
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

-- game.lua: rules of Goose Doctor. Owner: @Akshat-Kalra.
-- Reads the goose's copper lines (D-pad button events), runs the stages and
-- the countdown, drives the LEDs, and tells ui.lua what to show. Never
-- creates widgets. v0: rules are placeholders until the open questions on #40
-- (what stars mean, timer format) are answered.

local M = {}

-- Tunables -------------------------------------------------------------------
local ROUND_MS = 60000         -- countdown length
local TOUCH_PENALTY_MS = 5000  -- time lost per wall touch
local START_STARS = 3          -- a wall touch costs one; 0 stars = failure
local LOCKOUT_MS = 500         -- one scrape = one penalty per wall zone
local TIME_UPDATE_MS = 100     -- how often the timer display is refreshed
local LED_FLASH_MS = 300       -- red flash on a touch

local B = badge.input.BUTTON
local K = badge.input.KIND

-- Which goose line is on which button. Confirm with app/diag on a real badge
-- and change it only here.
local LINES = {
  [B.UP] = { kind = "wall", zone = 1 },
  [B.DOWN] = { kind = "wall", zone = 2 },
  [B.LEFT] = { kind = "seat_a" },    -- held while organ A sits in its seat
  [B.RIGHT] = { kind = "seat_b" },   -- pressed when organ B is delivered
}

-- State ----------------------------------------------------------------------
local ui
local screen = "start"             -- start | operating | success | failure
local stage = "remove"             -- remove | deliver (while operating)
local started_at, penalty_ms, stars = 0, 0, START_STARS
local locked_until = {}            -- wall zone -> ms
local next_time_update = 0
local best_ms = 0                  -- fastest success, 0 = none yet
local flash_until = 0

-- LEDs -----------------------------------------------------------------------
-- 1 upper left, 2 upper right, 3 middle right, 4 bottom right, 5 bottom left,
-- 6 middle left. 4 and 5 sit under the goose.
local function leds(r, g, b, only_bottom)
  badge.led.clear()
  if only_bottom then
    badge.led.set(4, r, g, b)
    badge.led.set(5, r, g, b)
  else
    badge.led.set_all(r, g, b)
  end
  badge.led.show()
end

local function idle_leds()
  if screen == "operating" then leds(40, 30, 0, true)
  elseif screen == "success" then leds(0, 120, 0)
  elseif screen == "failure" then leds(120, 0, 0)
  else leds(0, 0, 0) end
end

-- Helpers --------------------------------------------------------------------
local function time_left(now)
  return ROUND_MS - (now - started_at) - penalty_ms
end

local function info(now)
  return { time_left_ms = math.max(0, time_left(now)), stars = stars,
           stage = stage, best_ms = best_ms > 0 and best_ms or nil }
end

local function go(name, now)
  screen = name
  flash_until = 0
  ui.show(name, info(now))
  idle_leds()
end

local function new_round(now)
  stage = "remove"
  started_at, penalty_ms, stars = now, 0, START_STARS
  locked_until = {}
  next_time_update = 0
  go("operating", now)
end

local function finish(won, now)
  if won then
    local elapsed = now - started_at
    if best_ms == 0 or elapsed < best_ms then
      best_ms = elapsed
      badge.store.set_int("best_ms", best_ms)
    end
  end
  go(won and "success" or "failure", now)
end

local function wall_touch(zone, now)
  if now < (locked_until[zone] or 0) then return end
  locked_until[zone] = now + LOCKOUT_MS
  penalty_ms = penalty_ms + TOUCH_PENALTY_MS
  stars = stars - 1
  badge.sys.log("touch wall " .. zone .. " stars=" .. stars)
  ui.touch(zone)
  ui.set_stars(math.max(0, stars))
  ui.set_time(math.max(0, time_left(now)))   -- show the time jump right away
  leds(255, 0, 0, true)
  flash_until = now + LED_FLASH_MS
  if stars <= 0 then finish(false, now) end
end

-- Driver interface (called by main.lua) --------------------------------------
function M.start(the_ui, now)
  ui = the_ui
  best_ms = badge.store.get_int("best_ms", 0)
  go("start", now)
end

function M.tick(now)
  if flash_until > 0 and now >= flash_until then
    flash_until = 0
    idle_leds()
  end
  if screen ~= "operating" then return end
  if time_left(now) <= 0 then
    finish(false, now)
  elseif now >= next_time_update then
    next_time_update = now + TIME_UPDATE_MS
    ui.set_time(time_left(now))
  end
end

function M.button(button, kind, now)
  local line = LINES[button]
  if screen == "operating" and line then
    if line.kind == "wall" and kind == K.PRESSED then
      wall_touch(line.zone, now)
    elseif line.kind == "seat_a" and kind == K.RELEASED and stage == "remove" then
      stage = "deliver"
      ui.show("operating", info(now))
    elseif line.kind == "seat_b" and kind == K.PRESSED and stage == "deliver" then
      finish(true, now)
    end
    return
  end

  if kind ~= K.PRESSED or screen == "operating" then return end
  if button == B.A then
    new_round(now)
  elseif button == B.B then
    badge.app.exit()
  end
end

function M.stop()
end

return M

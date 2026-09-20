-- game.lua: rules of Goose Doctor. Owner: @Akshat-Kalra.
--
-- Real board (goose v3, see goose/README.md and the root CLAUDE.md "Circuit"
-- / "Goose layout" / "Current board" bullets): the plate covers SW2, SW3,
-- SW4, SW5, SW8 and SW10 with relief pockets (never pressed), and only two
-- switches are exposed through cut-outs: SW7 (HOME -- the firmware
-- intercepts it to exit the app, so it never reaches on_button here) and
-- SW6 (SW_HPM), the only button the player can actually press. Three copper
-- nets on the goose are wired to D-pad lines via pogo pins (tweezers tied to
-- GND; touching copper = that button pressed):
--   PENALTY (head/neck/back trace + breast/belly trace, joined) -> RIGHT
--   GOAL_1  (tail loop)                                          -> UP
--   GOAL_2  (belly loop)                                         -> LEFT
-- PENALTY has a 10 uF cap to GND to stretch brief touches so the button scan
-- doesn't miss them; that cap is charging for a moment after boot, so this
-- file ignores all three goose lines for INPUT_GRACE_MS after start and
-- again at the top of every round.
--
-- Reads those D-pad button events, runs the two goal stages and the
-- countdown, drives the LEDs, and tells ui.lua what to show. Never creates
-- widgets. A round fails only when time runs out; each PENALTY touch costs
-- TOUCH_PENALTY_MS.

local M = {}

-- Tunables -------------------------------------------------------------------
local ROUND_MS = 60000         -- countdown length
local TOUCH_PENALTY_MS = 5000  -- time lost per PENALTY touch
local LOCKOUT_MS = 500         -- one scrape = one penalty, then ignored a while
local TIME_UPDATE_MS = 100     -- how often the timer display is refreshed
local LED_FLASH_MS = 300       -- red flash on a touch
local LED_FRAME_MS = 50        -- LED animation frame time
local WARN_MS = 10000          -- last seconds: all LEDs blink red
local BREATHE_MS = 2000        -- start screen breathing period
local CHASE_MS = 2000          -- success chase length, then solid green
local CHASE_STEP_MS = 100      -- success chase speed
local STAGE_PULSE_MS = 250     -- green pulse when goal 1 (tail) is reached
local INPUT_GRACE_MS = 500     -- ignore goose lines this long after boot and
                                -- after each round start, while the PENALTY
                                -- line's 10 uF cap is still charging

local B = badge.input.BUTTON
local K = badge.input.KIND

-- Which goose line is on which D-pad button (see the header comment above).
-- Confirmed by wiring on goose v3; nothing else may hard-code a button.
local LINES = {
  [B.RIGHT] = { kind = "penalty" },
  [B.UP] = { kind = "goal1" },
  [B.LEFT] = { kind = "goal2" },
}

-- SW6 is the only exposed, usable button (SW7/HOME is intercepted by the
-- firmware and never reaches on_button). We don't yet know which
-- badge.input.BUTTON constant SW6 reports -- the diag app will confirm it.
-- Until then, accept any of these as start/retry.
local START_BUTTONS = { [B.A] = true, [B.B] = true, [B.AUX1] = true }

-- State ----------------------------------------------------------------------
local ui
local screen = "start"             -- start | operating | success | failure
local stage = "goal1"               -- goal1 | goal2 (while operating)
local started_at, penalty_ms = 0, 0
local penalty_locked_until = 0     -- ms; PENALTY ignored until this time
local next_time_update = 0
local best_ms = 0                  -- fastest success, 0 = none yet
local grace_until = 0               -- ignore goose lines until this ms

-- Helpers --------------------------------------------------------------------
local function time_left(now)
  return ROUND_MS - (now - started_at) - penalty_ms
end

local function info(now)
  return { time_left_ms = math.max(0, time_left(now)), stage = stage,
           best_ms = best_ms > 0 and best_ms or nil }
end

-- LEDs -----------------------------------------------------------------------
-- 1 upper left, 2 upper right, 3 middle right, 4 bottom right, 5 bottom left,
-- 6 middle left. 4 and 5 sit under the goose. Each frame is the current
-- screen's pattern plus at most one short effect on top, shown once.
local CLOCKWISE = { 1, 2, 3, 4, 5, 6 }
local fr, fg, fb = {}, {}, {}      -- frame being built (reused, no garbage)
local effect, effect_start, effect_until = nil, 0, 0   -- "touch" | "stage"
local screen_since = 0
local next_frame = 0

local function fill(r, g, b)
  for i = 1, 6 do fr[i], fg[i], fb[i] = r, g, b end
end

local function put(i, r, g, b)
  fr[i], fg[i], fb[i] = r, g, b
end

-- Triangle wave 0 -> 1 -> 0 over period ms.
local function wave(now, period)
  local t = (now % period) / period
  return t < 0.5 and t * 2 or (1 - t) * 2
end

local function base_frame(now)
  if screen == "start" then
    local k = 0.1 + 0.4 * wave(now, BREATHE_MS)          -- slow yellow breathing
    fill(math.floor(255 * k), math.floor(180 * k), 0)
  elseif screen == "operating" then
    local left = math.max(0, time_left(now))
    if left <= WARN_MS then                                -- last seconds: blink red
      if now % 500 < 250 then fill(255, 0, 0) else fill(0, 0, 0) end
    else                                                   -- countdown drains clockwise
      local f = left / ROUND_MS
      local g = f > 0.5 and 180 or (f > 0.25 and 90 or 0)   -- yellow, orange, red
      fill(0, 0, 0)
      for n = 1, math.ceil(6 * f) do put(CLOCKWISE[n], 255, g, 0) end
    end
  elseif screen == "success" then
    local age = now - screen_since
    if age < CHASE_MS then                                 -- green chase, then solid
      fill(0, 40, 0)
      put(CLOCKWISE[math.floor(age / CHASE_STEP_MS) % 6 + 1], 0, 255, 0)
    else
      fill(0, 160, 0)
    end
  elseif screen == "failure" then
    fill(math.floor(40 + 160 * wave(now, 1200)), 0, 0)     -- slow red pulse
  else
    fill(0, 0, 0)
  end
end

local function effect_frame(now)
  if not effect then return end
  if now >= effect_until then
    effect = nil
  elseif effect == "touch" then                            -- red under the goose
    put(4, 255, 0, 0)
    put(5, 255, 0, 0)
  elseif effect == "stage" then                            -- goal 1 reached: green pulse
    fill(0, 255, 0)
  end
end

local function render(now)
  base_frame(now)
  effect_frame(now)
  for i = 1, 6 do badge.led.set(i, fr[i], fg[i], fb[i]) end
  badge.led.show()
end

local function start_effect(name, ms, now)
  effect, effect_start, effect_until = name, now, now + ms
  render(now)
end


local function go(name, now)
  screen = name
  screen_since = now
  effect = nil
  ui.show(name, info(now))
  render(now)
end

local function new_round(now)
  stage = "goal1"
  started_at, penalty_ms = now, 0
  penalty_locked_until = 0
  next_time_update = 0
  grace_until = now + INPUT_GRACE_MS
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

local function penalty_touch(now)
  if now < penalty_locked_until then return end
  penalty_locked_until = now + LOCKOUT_MS
  penalty_ms = penalty_ms + TOUCH_PENALTY_MS
  badge.sys.log("touch penalty")
  ui.touch(1)
  ui.set_time(math.max(0, time_left(now)))   -- show the time jump right away
  start_effect("touch", LED_FLASH_MS, now)
end

local function goal_touch(kind, now)
  if kind == "goal1" and stage == "goal1" then
    stage = "goal2"
    ui.show("operating", info(now))
    start_effect("stage", STAGE_PULSE_MS, now)
  elseif kind == "goal2" and stage == "goal2" then
    finish(true, now)
  end
  -- goal2 touched during stage "goal1" does nothing (see root CLAUDE.md).
end

-- Driver interface (called by main.lua) --------------------------------------
function M.start(the_ui, now)
  ui = the_ui
  best_ms = badge.store.get_int("best_ms", 0)
  grace_until = now + INPUT_GRACE_MS
  go("start", now)
end

function M.tick(now)
  if screen == "operating" then
    if time_left(now) <= 0 then
      finish(false, now)
    elseif now >= next_time_update then
      next_time_update = now + TIME_UPDATE_MS
      ui.set_time(time_left(now))
    end
  end
  if now >= next_frame then
    next_frame = now + LED_FRAME_MS
    render(now)
  end
end

function M.button(button, kind, now)
  local line = LINES[button]
  if line then
    if kind == K.PRESSED and screen == "operating" and now >= grace_until then
      if line.kind == "penalty" then
        penalty_touch(now)
      else
        goal_touch(line.kind, now)
      end
    end
    return
  end

  if kind ~= K.PRESSED or screen == "operating" then return end
  if START_BUTTONS[button] then
    new_round(now)
  end
end

function M.stop()
end

return M

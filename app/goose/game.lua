-- game.lua: rules of Goose Doctor. Owner: @Akshat-Kalra.
-- Reads the goose's copper lines (D-pad button events), runs the stages and
-- the countdown, drives the LEDs, and tells ui.lua what to show. Never
-- creates widgets. A round fails only when time runs out; each wall touch
-- costs TOUCH_PENALTY_MS (stars were dropped, see #40).

local M = {}

-- Tunables -------------------------------------------------------------------
local ROUND_MS = 60000         -- countdown length
local TOUCH_PENALTY_MS = 5000  -- time lost per wall touch
local LOCKOUT_MS = 500         -- one scrape = one penalty per wall zone
local TIME_UPDATE_MS = 100     -- how often the timer display is refreshed
local LED_FLASH_MS = 300       -- red flash on a touch
local LED_FRAME_MS = 50        -- LED animation frame time
local WARN_MS = 10000          -- last seconds: all LEDs blink red
local BREATHE_MS = 2000        -- start screen breathing period
local CHASE_MS = 2000          -- success chase length, then solid green
local CHASE_STEP_MS = 100      -- success chase speed
local STAGE_PULSE_MS = 250     -- green pulse when organ A is out
local REFUSED_MS = 600         -- amber blink when A is pressed without organ A seated

-- SEAT_SETTLE_MS and REQUIRE_SEATED are overridable for playtests, because the
-- badge console's `press` command only taps (PRESSED then RELEASED a few ms
-- later, see app/tools/badge.py Session docs) -- it can't hold a button down
-- the way a real seated organ does. `M.start` reads these once from the app
-- store; defaults match the real game exactly, and a real badge/build never
-- has these keys set. app/tools/playtest.py sets them via `config
-- goose_doctor t_seated 0` / `t_settle_ms 0` and restores the defaults after.
local SEAT_SETTLE_MS = 150     -- a seat must stay open/closed this long to count;
                               -- stops a wobbling organ or a tweezer brush on a
                               -- seat pad (tweezers are GND too) from counting
local REQUIRE_SEATED = true    -- A starts a round only with organ A in its seat

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

local SEAT_A, SEAT_B
for button, line in pairs(LINES) do
  if line.kind == "seat_a" then SEAT_A = button end
  if line.kind == "seat_b" then SEAT_B = button end
end

-- State ----------------------------------------------------------------------
local ui
local screen = "start"             -- start | operating | success | failure
local stage = "remove"             -- remove | deliver (while operating)
local started_at, penalty_ms = 0, 0
local locked_until = {}            -- wall zone -> ms
local next_time_update = 0
local best_ms = 0                  -- fastest success, 0 = none yet
local down = {}                    -- goose line -> true while pressed (from events)
local changed_at = {}              -- goose line -> ms of its last press/release
local seat_a_seen_down = false     -- organ A observed seated at least once this
                                    -- round; guards check_seats() below against
                                    -- the default "never touched" (down=false)
                                    -- state looking like an instant removal when
                                    -- REQUIRE_SEATED is off (t_seated=0 playtest
                                    -- knob) and a round starts before organ A
                                    -- has ever been in its seat this session

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
local effect, effect_start, effect_until = nil, 0, 0   -- "touch" | "stage" | "refused"
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
  elseif effect == "stage" then                            -- organ A out: green pulse
    fill(0, 255, 0)
  elseif effect == "refused" then                          -- amber blink: seat organ A
    if math.floor((now - effect_start) / 100) % 2 == 0 then fill(255, 120, 0)
    else fill(0, 0, 0) end
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
  stage = "remove"
  started_at, penalty_ms = now, 0
  locked_until = {}
  next_time_update = 0
  seat_a_seen_down = down[SEAT_A] or false
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
  badge.sys.log("touch wall " .. zone)
  ui.touch(zone)
  ui.set_time(math.max(0, time_left(now)))   -- show the time jump right away
  start_effect("touch", LED_FLASH_MS, now)
end

-- True when a line has been in the given state for at least SEAT_SETTLE_MS.
local function settled(button, want_down, now)
  return (down[button] or false) == want_down
     and now - (changed_at[button] or 0) >= SEAT_SETTLE_MS
end

local function check_seats(now)
  if stage == "remove" and seat_a_seen_down and settled(SEAT_A, false, now) then
    stage = "deliver"
    ui.show("operating", info(now))
    start_effect("stage", STAGE_PULSE_MS, now)
  elseif stage == "deliver" and settled(SEAT_B, true, now) then
    finish(true, changed_at[SEAT_B])   -- time the win from the actual contact
  end
end

-- Driver interface (called by main.lua) --------------------------------------
function M.start(the_ui, now)
  ui = the_ui
  best_ms = badge.store.get_int("best_ms", 0)
  SEAT_SETTLE_MS = badge.store.get_int("t_settle_ms", SEAT_SETTLE_MS)
  REQUIRE_SEATED = badge.store.get_int("t_seated", REQUIRE_SEATED and 1 or 0) == 1
  go("start", now)
end

function M.tick(now)
  if screen == "operating" then check_seats(now) end
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
    -- Track every goose line on every screen, so the seat state is known
    -- before a round starts. Seats are acted on in tick, once settled.
    down[button] = kind == K.PRESSED
    changed_at[button] = now
    if button == SEAT_A and down[button] then seat_a_seen_down = true end
    if screen == "operating" and line.kind == "wall" and kind == K.PRESSED then
      wall_touch(line.zone, now)
    elseif screen == "operating" and (line.kind == "seat_a" or line.kind == "seat_b") then
      -- Also check right on the event, not just every tick: with the real
      -- SEAT_SETTLE_MS this changes nothing (elapsed since changed_at is 0,
      -- so settled() still needs a later tick once it's genuinely held), but
      -- it lets t_settle_ms=0 register a seat change from a single console
      -- `press` tap (PRESSED then RELEASED within the same call), which a
      -- tick loop sampled every ~20 ms would otherwise never catch.
      check_seats(now)
    end
    return
  end

  if kind ~= K.PRESSED or screen == "operating" then return end
  if button == B.A then
    if REQUIRE_SEATED and not down[SEAT_A] then
      badge.sys.log("start refused: organ A is not in its seat")
      start_effect("refused", REFUSED_MS, now)
      return
    end
    new_round(now)
  elseif button == B.B then
    badge.app.exit()
  end
end

function M.stop()
end

return M

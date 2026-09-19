-- Headless tests for the badge apps (the badge has no simulator).
--   python app/tools/badge.py build goose && ... preview && ... diag
--   lua app/tools/test.lua
-- Loads each built single-file app from app/dist/ in a sandbox like the
-- badge's (no pcall/setmetatable/os/io/load), with a mock badge API.
-- 1. Smoke test: every app survives enter / ticks / every button / exit.
-- 2. Game rules: game.lua against a fake ui that records contract calls.
--    These don't depend on how ui.lua draws, so the UI can change freely.

local dist = arg[0]:gsub("tools/test%.lua$", "dist/")
local failures = 0

local function check(cond, msg)
  if not cond then
    failures = failures + 1
    print("  FAIL: " .. msg)
  end
end

-- Mock badge --------------------------------------------------------------
local function new_badge()
  local st = { clock = 0, leds = {}, store = {}, exited = false, logs = {} }
  local W = {}
  W.__index = W
  local function widget(kind, parent)
    return setmetatable({ kind = kind, parent = parent, text = "", hidden_ = false }, W)
  end
  for _, m in ipairs({ "set_pos", "set_size", "align", "style", "set_color",
                       "set_border", "set_font_size", "bring_to_front", "set_value",
                       "set_range", "set_src", "set_points", "clickable" }) do
    W[m] = function() end
  end
  function W:set_text(s)
    assert(type(s) == "string", "set_text needs a string")
    assert(#s <= 1024, "text over 1024 bytes")
    self.text = s
  end
  function W:hidden(h) self.hidden_ = h end
  local count = 0
  local function factory(kind)
    return function(parent, a)
      count = count + 1
      assert(count <= 512, "over 512 widgets")
      local w = widget(kind, parent)
      if kind == "label" then w.text = a or "" end
      return w
    end
  end
  local B = { A = 1, B = 2, HOME = 3, DOWN = 4, LEFT = 5, RIGHT = 6, UP = 7, AUX1 = 8, START = 9 }
  st.badge = {
    ui = { label = factory("label"), box = factory("box"), bar = factory("bar"),
           arc = factory("arc"), line = factory("line"), image = factory("image"),
           button = factory("button"), screen_width = 320, screen_height = 240 },
    input = { BUTTON = B, KIND = { PRESSED = 1, RELEASED = 2 },
              is_down = function() return false end, held = function() return 0 end },
    sys = { ms = function() return st.clock end, version = function() return "mock" end,
            log = function(s) st.logs[#st.logs + 1] = s end,
            random = function(n) return n and 0 or 4 end },
    led = { count = function() return 6 end, show = function() end,
            clear = function() st.leds = {} end,
            set_all = function(r, g, b) for i = 1, 6 do st.leds[i] = { r, g, b } end end,
            set = function(i, r, g, b)
              assert(math.type(i) == "integer" and i >= 1 and i <= 6, "bad LED index")
              for _, c in ipairs({ r, g, b }) do
                assert(math.type(c) == "integer" and c >= 0 and c <= 255, "bad LED value")
              end
              st.leds[i] = { r, g, b }
            end },
    store = { get_int = function(k, d) return st.store[k] or d end,
              set_int = function(k, v) st.store[k] = v end },
    app = { exit = function() st.exited = true end },
  }
  return st
end

local function sandbox(badge)
  local env = { badge = badge }
  for _, k in ipairs({ "assert", "error", "ipairs", "next", "pairs", "print", "select",
                       "tonumber", "tostring", "type", "rawequal", "rawget", "rawset",
                       "rawlen", "getmetatable" }) do
    env[k] = _G[k]
  end
  env.table, env.string, env.math, env.utf8 = table, string, math, utf8
  return env
end

local function load_app(file, badge)
  local f = assert(io.open(dist .. file, "r"), "missing " .. dist .. file .. " (run badge.py build first)")
  local src = f:read("a")
  f:close()
  local env = sandbox(badge)
  local chunk, err = load(src, "@" .. file, "t", env)
  assert(chunk, err)
  chunk()
  return env
end

-- 1. Smoke tests ----------------------------------------------------------
local function smoke(file)
  print(file)
  local st = new_badge()
  local ok, err = pcall(function()
    local app = load_app(file, st.badge)
    app.on_enter({})
    for step = 1, 3 do
      for b = 1, 9 do
        st.clock = st.clock + 37
        app.on_button(b, 1)
        if app.on_tick then app.on_tick() end
        st.clock = st.clock + 20
        app.on_button(b, 2)
        if app.on_tick then app.on_tick() end
      end
      for _ = 1, 200 do
        st.clock = st.clock + 20
        if app.on_tick then app.on_tick() end
      end
    end
    if app.on_exit then app.on_exit() end
  end)
  check(ok, "crashed: " .. tostring(err))
end

smoke("goose_diag.lua")
smoke("goose_preview.lua")
smoke("goose_doctor.lua")

-- 2a. ui.lua honours the contract (this is what protects game.lua from ui edits)
print("ui.lua contract")
do
  local st = new_badge()
  local env = sandbox(st.badge)
  local f = assert(io.open(dist .. "goose_doctor/ui.lua", "r"))
  local ui = assert(load(f:read("a"), "@ui.lua", "t", env))()
  f:close()
  for _, fn in ipairs({ "init", "show", "set_time", "touch", "tick" }) do
    check(type(ui[fn]) == "function", "ui." .. fn .. " must be a function")
  end
  local ok, err = pcall(function()
    ui.init({})
    for _, name in ipairs({ "start", "operating", "success", "failure" }) do
      for _, stage in ipairs({ "goal1", "goal2" }) do
        ui.show(name, { time_left_ms = 59999, stage = stage, best_ms = 12340 })
        ui.show(name, { time_left_ms = 0, stage = stage, best_ms = nil })
      end
    end
    for _, ms in ipairs({ 0, 1, 9999, 60000, 3599999 }) do ui.set_time(ms) end
    ui.touch(1)
    for now = 0, 2000, 20 do ui.tick(now) end
  end)
  check(ok, "contract call failed: " .. tostring(err))
end

-- 2. Game rules against a recording ui ------------------------------------
-- LINES: RIGHT = PENALTY, UP = GOAL_1 (tail), LEFT = GOAL_2 (belly).
-- START_BUTTONS: A, B or AUX1 (SW6's real constant is unconfirmed -- see
-- app/CLAUDE.md). INPUT_GRACE_MS = 500 ignores goose lines for the first
-- 500 ms of each round (the PENALTY cap is still charging).
print("game.lua rules")
do
  local function load_game(st)
    local f = assert(io.open(dist .. "goose_doctor/game.lua", "r"))
    local game = assert(load(f:read("a"), "@game.lua", "t", sandbox(st.badge)))()
    f:close()
    return game
  end

  local GRACE = 500

  local st = new_badge()
  local B = st.badge.input.BUTTON
  local calls = { touches = {} }
  local fake_ui = {    -- game.lua only knows ui through the contract
    init = function() end,
    tick = function() end,
    show = function(name, info) calls.screen, calls.info = name, info end,
    set_time = function(ms) calls.time = ms end,
    touch = function(zone) calls.touches[#calls.touches + 1] = zone end,
  }
  local game = load_game(st)
  game.start(fake_ui, st.clock)
  local function btn(b, kind) game.button(b, kind, st.clock) end
  local function tick(ms)
    local stop = st.clock + ms
    while st.clock < stop do
      st.clock = st.clock + 20
      game.tick(st.clock)
    end
  end

  check(calls.screen == "start", "starts on the start screen")
  btn(B.UP, 1); btn(B.UP, 2); btn(B.RIGHT, 1); btn(B.RIGHT, 2); btn(B.LEFT, 1); btn(B.LEFT, 2)
  check(#calls.touches == 0, "goose lines are ignored before the round starts")
  check(st.leds[1][1] > 0 and st.leds[1][3] == 0, "start screen breathes yellow")

  btn(B.A, 1)
  local round_start = st.clock
  check(calls.screen == "operating" and calls.info.stage == "goal1", "A starts a round on stage goal1")

  btn(B.RIGHT, 1); btn(B.RIGHT, 2)
  check(#calls.touches == 0, "PENALTY is ignored during the input grace window")
  check(st.clock - round_start < GRACE, "grace check ran before the window elapsed")
  tick(1000)   -- also clears the input grace window (500 ms)
  check(calls.time and calls.time <= 59100 and calls.time >= 59000, "timer counts down (refreshed every 100 ms)")

  btn(B.RIGHT, 1); btn(B.RIGHT, 2)
  check(#calls.touches == 1, "PENALTY counts once the grace window has passed")
  check(calls.time == 60000 - (st.clock - round_start) - 5000,
        "a touch costs 5 s, shown immediately (" .. calls.time .. ")")
  check(st.leds[4] and st.leds[4][1] == 255, "bottom LEDs flash red on a touch")

  btn(B.RIGHT, 1); btn(B.RIGHT, 2)
  check(#calls.touches == 1, "a second scrape inside the lockout counts once")
  tick(600)
  check(st.leds[4] and st.leds[4][2] > 0, "touch flash ends (countdown colour is back)")

  btn(B.LEFT, 1); btn(B.LEFT, 2)
  check(calls.screen == "operating" and calls.info.stage == "goal1",
        "GOAL_2 during stage goal1 does nothing")
  check(#calls.touches == 1, "GOAL_2 before GOAL_1 is not a penalty either")

  btn(B.UP, 1); btn(B.UP, 2)
  check(calls.info.stage == "goal2", "GOAL_1 advances to stage goal2")
  check(st.leds[1][2] == 255 and st.leds[1][1] == 0, "green pulse on reaching GOAL_1")

  btn(B.UP, 1); btn(B.UP, 2)
  check(calls.screen == "operating" and calls.info.stage == "goal2",
        "touching GOAL_1 again during stage goal2 does nothing")

  btn(B.LEFT, 1)
  local delivered_at = st.clock
  btn(B.LEFT, 2)
  check(calls.screen == "success", "GOAL_2 during stage goal2 wins")
  check(st.store.best_ms == delivered_at - round_start, "best time counts to the moment of contact")
  local lit = 0
  for i = 1, 6 do if st.leds[i][2] == 255 then lit = lit + 1 end end
  check(lit == 1 and st.leds[1][1] == 0, "success starts a green chase (one bright LED)")
  tick(2100)
  check(st.leds[3][2] == 160 and st.leds[6][2] == 160, "chase ends in solid green")

  btn(B.B, 1)   -- retry with a different accepted start button
  check(calls.screen == "operating" and calls.info.stage == "goal1", "B retries with a fresh round")
  tick(61000)
  check(calls.screen == "failure", "running out of time fails")

  btn(B.AUX1, 1)   -- retry with the third accepted start button
  check(calls.screen == "operating", "AUX1 also starts/retries a round")
  tick(GRACE + 20)
  for _ = 1, 12 do btn(B.RIGHT, 1); btn(B.RIGHT, 2); tick(600) end
  check(calls.screen == "failure", "PENALTY touches eat the clock until time runs out")
end

-- 3. LED countdown ------------------------------------------------------------
print("game.lua LEDs")
do
  local st = new_badge()
  local B = st.badge.input.BUTTON
  local noop = function() end
  local fake_ui = { init = noop, tick = noop, show = noop, set_time = noop, touch = noop }
  local f = assert(io.open(dist .. "goose_doctor/game.lua", "r"))
  local game = assert(load(f:read("a"), "@game.lua", "t", sandbox(st.badge)))()
  f:close()
  local function tick(ms)
    local stop = st.clock + ms
    while st.clock < stop do
      st.clock = st.clock + 20
      game.tick(st.clock)
    end
  end
  local function lit()
    local n = 0
    for i = 1, 6 do if st.leds[i] and st.leds[i][1] > 0 then n = n + 1 end end
    return n
  end
  game.start(fake_ui, st.clock)
  game.button(B.A, 1, st.clock)
  tick(100)
  check(lit() == 6 and st.leds[1][2] == 180, "full time: all 6 LEDs yellow")
  tick(25000)                      -- 35 s left of 60
  check(lit() == 4 and st.leds[1][2] == 180, "35 s left: 4 LEDs, still yellow (" .. lit() .. ")")
  tick(10000)                      -- 25 s left
  check(lit() == 3 and st.leds[1][2] == 90, "25 s left: 3 LEDs, orange (" .. lit() .. ")")
  tick(14000)                      -- 11 s left
  check(lit() == 2 and st.leds[1][2] == 0, "11 s left: 2 LEDs, red (" .. lit() .. ")")
  tick(1500)                       -- 9.5 s left: warning mode
  local seen_on, seen_off = false, false
  for _ = 1, 30 do
    tick(20)
    if lit() == 6 then seen_on = true elseif lit() == 0 then seen_off = true end
  end
  check(seen_on and seen_off, "last 10 s: all LEDs blink red")
  game.button(B.RIGHT, 1, st.clock)
  check(st.leds[4][1] == 255 and st.leds[5][1] == 255, "a touch lights the bottom LEDs red even while blinking")
end

print(failures == 0 and "ALL TESTS PASSED" or (failures .. " FAILED"))
os.exit(failures == 0 and 0 or 1)

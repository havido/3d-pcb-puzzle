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

-- 2. Game rules against a recording ui ------------------------------------
print("game.lua rules")
do
  local st = new_badge()
  local B = st.badge.input.BUTTON
  local calls = { touches = {} }
  local fake_ui = {    -- game.lua only knows ui through the contract
    init = function() end,
    tick = function() end,
    show = function(name, info) calls.screen, calls.info = name, info end,
    set_time = function(ms) calls.time = ms end,
    set_stars = function(n) calls.stars = n end,
    touch = function(zone) calls.touches[#calls.touches + 1] = zone end,
  }
  local env = sandbox(st.badge)
  local f = assert(io.open(dist .. "goose_doctor/game.lua", "r"))
  local game = assert(load(f:read("a"), "@game.lua", "t", env))()
  f:close()
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
  btn(B.UP, 1)
  check(#calls.touches == 0, "wall touches are ignored before the round starts")

  btn(B.A, 1)
  local round_start = st.clock
  check(calls.screen == "operating" and calls.info.stage == "remove", "A starts a round in stage remove")
  check(calls.info.stars == 3, "round starts with 3 stars")
  tick(1000)
  check(calls.time and calls.time <= 59100 and calls.time >= 59000, "timer counts down (refreshed every 100 ms) (" .. tostring(calls.time) .. ")")

  btn(B.UP, 1); btn(B.UP, 2); btn(B.UP, 1); btn(B.UP, 2)
  check(#calls.touches == 1 and calls.stars == 2, "a scrape inside the lockout counts once")
  check(st.leds[4] and st.leds[4][1] == 255, "bottom LEDs flash red on a touch")
  tick(600)
  check(st.leds[4] and st.leds[4][1] < 255, "LED flash ends")
  btn(B.DOWN, 1)
  check(#calls.touches == 2 and calls.touches[2] == 2, "wall 2 is a separate zone")
  check(calls.time == 60000 - (st.clock - round_start) - 10000,
        "each touch costs 5 s, shown immediately (" .. calls.time .. ")")
  tick(200)

  btn(B.RIGHT, 1)
  check(calls.screen == "operating", "delivering before removing does nothing")
  btn(B.LEFT, 1); btn(B.LEFT, 2)
  check(calls.info.stage == "deliver", "lifting organ A moves to stage deliver")
  btn(B.RIGHT, 1)
  check(calls.screen == "success", "seating organ B wins")
  check(st.store.best_ms and st.store.best_ms > 0, "best time is saved")
  check(st.leds[1] and st.leds[1][2] > 0, "success lights green")

  btn(B.A, 1)
  check(calls.screen == "operating" and calls.info.stars == 3 and calls.info.stage == "remove", "A retries with a fresh round")
  tick(61000)
  check(calls.screen == "failure", "running out of time fails")

  btn(B.A, 1)
  btn(B.UP, 1); tick(600); btn(B.UP, 1); tick(600); btn(B.UP, 1)
  check(calls.screen == "failure", "losing all stars fails")

  btn(B.B, 1)
  check(st.exited, "B quits from the result screen")
end

print(failures == 0 and "ALL TESTS PASSED" or (failures .. " FAILED"))
os.exit(failures == 0 and 0 or 1)

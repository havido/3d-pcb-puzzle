-- preview.lua: fake game for building screens without the goose or game.lua.
-- Built as the separate app "Goose UI Preview" (slug goose_preview).
--   A      next screen          LEFT   previous screen
--   B      touch wall 1         RIGHT  touch wall 2
--   UP     +1 star              DOWN   -1 star
--   START  switch stage (remove / deliver)
-- On the operating screen a fake timer counts down from 60 s and loops.

local M = {}

local ORDER = { "start", "operating", "success", "failure" }
local B = badge.input.BUTTON
local K = badge.input.KIND

local ui
local index = 1
local stars, stage = 3, "remove"
local timer_start, next_update = 0, 0

local function info(now)
  return { time_left_ms = 60000 - (now - timer_start) % 60000, stars = stars,
           stage = stage, best_ms = 42420 }
end

local function show(now)
  badge.sys.log("preview: " .. ORDER[index] .. " stars=" .. stars .. " stage=" .. stage)
  ui.show(ORDER[index], info(now))
end

function M.start(the_ui, now)
  ui = the_ui
  timer_start = now
  show(now)
end

function M.tick(now)
  if ORDER[index] == "operating" and now >= next_update then
    next_update = now + 100
    ui.set_time(info(now).time_left_ms)
  end
end

function M.button(button, kind, now)
  if kind ~= K.PRESSED then return end
  if button == B.A then
    index = index % #ORDER + 1
    show(now)
  elseif button == B.LEFT then
    index = (index - 2) % #ORDER + 1
    show(now)
  elseif button == B.B then
    ui.touch(1)
  elseif button == B.RIGHT then
    ui.touch(2)
  elseif button == B.UP then
    stars = math.min(5, stars + 1)
    ui.set_stars(stars)
  elseif button == B.DOWN then
    stars = math.max(0, stars - 1)
    ui.set_stars(stars)
  elseif button == B.START then
    stage = stage == "remove" and "deliver" or "remove"
    show(now)
  end
end

function M.stop()
end

return M

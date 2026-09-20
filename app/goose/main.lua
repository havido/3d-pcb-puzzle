-- Goose Doctor: lifecycle only. Connects game.lua to the screens in ui.lua.
-- The manifest lives in tools/badge.py (TARGETS), not here.

local ui = require("ui")
local game = require("game")

function on_enter(root)
  ui.init(root)
  game.start(ui, badge.sys.ms())
end

function on_tick()
  local now = badge.sys.ms()
  game.tick(now)
  ui.tick(now)
end

function on_button(button, kind)
  game.button(button, kind, badge.sys.ms())
end

function on_exit()
  game.stop()
  badge.led.clear()
  badge.led.show()
end

-- Goose Doctor: lifecycle only. Connects a driver to the screens in ui.lua.
-- The driver is game.lua in the real app (goose_doctor) and preview.lua in
-- the UI preview app (goose_preview); tools/badge.py generates driver.lua.
-- The manifest lives in tools/badge.py (TARGETS), not here.

local ui = require("ui")
local driver = require("driver")

function on_enter(root)
  ui.init(root)
  driver.start(ui, badge.sys.ms())
end

function on_tick()
  local now = badge.sys.ms()
  driver.tick(now)
  ui.tick(now)
end

function on_button(button, kind)
  driver.button(button, kind, badge.sys.ms())
end

function on_exit()
  driver.stop()
  badge.led.clear()
  badge.led.show()
end

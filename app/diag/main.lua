--[==[badge-app
slug=goose_diag
name=Goose Diag
icon=DG
api=2
heap_kb=48
wake_lock=1
]==]

-- Goose diagnostic (#19): shows every button line live and how long each
-- press lasted, to map the D-pad pads, run Gate 0 and check missed touches.
-- Every press/release is also logged to the IDE console (badge.sys.log).
-- Controls: START resets the stats. HOME exits.
-- Timings are taken when the event reaches Lua, so they are only as precise
-- as the firmware's button scan; very short touches may show as 0 ms or be lost.

local IDLE_BG = 0x2a2f38
local HELD_BG = 0xd83a3a
local LOG_LINES = 9

local B = badge.input.BUTTON
local K = badge.input.KIND

local names = {}          -- button value -> "UP", "A", ...
for name, value in pairs(B) do names[value] = name end

local DPAD = { B.UP, B.LEFT, B.RIGHT, B.DOWN }
local is_dpad = {}
for _, b in ipairs(DPAD) do is_dpad[b] = true end

local t0 = 0
local down_at = {}        -- button -> ms of its last press
local presses = {}        -- button -> press count
local shortest = {}       -- button -> shortest hold, ms
local best_ms, best_name = nil, nil

local cells = {}          -- button -> { box = , label = }
local log_label, short_label
local log = {}

-- Seconds with one decimal, to keep log lines short (the console has full ms).
local function fmt_time(ms)
  return string.format("%.1f", ms / 1000)
end

local function add_log(line)
  table.insert(log, 1, line)
  if #log > LOG_LINES then table.remove(log) end
  log_label:set_text(table.concat(log, "\n"))
end

local function cell_text(b)
  local s = names[b] .. "\n" .. (presses[b] or 0)
  if shortest[b] then s = s .. " " .. shortest[b] .. "ms" end
  return s
end

local function refresh_cell(b)
  local c = cells[b]
  if not c then return end
  c.box:set_color(down_at[b] and HELD_BG or IDLE_BG)
  c.label:set_text(cell_text(b))
end

local function refresh_short()
  if best_ms then
    short_label:set_text("Shortest press: " .. best_ms .. " ms (" .. best_name .. ")")
  else
    short_label:set_text("Shortest press: -")
  end
end

-- Bottom LEDs (under the goose) glow red while any D-pad line is held.
local function refresh_leds()
  local any = false
  for _, b in ipairs(DPAD) do
    if down_at[b] then any = true end
  end
  badge.led.clear()
  if any then
    badge.led.set(4, 255, 0, 0)
    badge.led.set(5, 255, 0, 0)
  end
  badge.led.show()
end

local function make_cell(root, b, x, y, w, h)
  local box = badge.ui.box(root, w, h)
  box:set_pos(x, y)
  box:style({ bg_color = IDLE_BG, radius = 6, border_width = 1,
              border_color = 0x6a7280, pad_all = 0 })
  local label = badge.ui.label(box, "")
  label:style({ text_font = 14, text_align = "center" })
  label:align("center", 0, 0)
  cells[b] = { box = box, label = label }
  refresh_cell(b)
end

local function reset_stats()
  presses, shortest = {}, {}
  best_ms, best_name = nil, nil
  for b in pairs(cells) do refresh_cell(b) end
  refresh_short()
end

function on_enter(root)
  t0 = badge.sys.ms()

  local title = badge.ui.label(root, "Goose Diag  fw " .. tostring(badge.sys.version()))
  title:style({ text_font = 14 })
  title:set_pos(6, 4)

  -- D-pad as a cross, other buttons in a row underneath.
  make_cell(root, B.UP,     60, 26, 56, 40)
  make_cell(root, B.LEFT,    2, 70, 56, 40)
  make_cell(root, B.RIGHT, 118, 70, 56, 40)
  make_cell(root, B.DOWN,   60, 114, 56, 40)
  local others = { B.A, B.B, B.START, B.AUX1 }
  for i, b in ipairs(others) do
    if b then make_cell(root, b, 2 + (i - 1) * 44, 158, 42, 38) end
  end

  -- Fixed size so long lines are cut off inside the screen.
  log_label = badge.ui.label(root, "Touch a line...")
  log_label:style({ text_font = 14 })
  log_label:set_pos(182, 26)
  log_label:set_size(136, 170)

  short_label = badge.ui.label(root, "")
  short_label:style({ text_font = 14 })
  short_label:set_pos(6, 200)
  refresh_short()

  local hint = badge.ui.label(root, "START reset stats   HOME exit")
  hint:style({ text_font = 14, text_color = 0x9aa3b0 })
  hint:set_pos(6, 220)

  refresh_leds()
end

function on_button(button, kind)
  local now = badge.sys.ms()
  local name = names[button] or tostring(button)
  local t = fmt_time(now - t0)

  if kind == K.PRESSED then
    if button == B.START then
      reset_stats()
      add_log(t .. " stats reset")
      return
    end
    down_at[button] = now
    presses[button] = (presses[button] or 0) + 1
    add_log(t .. " " .. name .. " down")
    badge.sys.log("down " .. name .. " t=" .. (now - t0))

  elseif kind == K.RELEASED then
    local since = down_at[button]
    down_at[button] = nil
    if since then
      local held = math.floor(now - since)
      if not shortest[button] or held < shortest[button] then
        shortest[button] = held
      end
      if is_dpad[button] and (not best_ms or held < best_ms) then
        best_ms, best_name = held, name
        refresh_short()
      end
      add_log(t .. " " .. name .. " up " .. held .. "ms")
      badge.sys.log("up " .. name .. " t=" .. (now - t0) .. " held=" .. held)
    elseif button ~= B.START then
      add_log(t .. " " .. name .. " up (no dn)")
    end
  end

  refresh_cell(button)
  if is_dpad[button] then refresh_leds() end
end

function on_exit()
  badge.led.clear()
  badge.led.show()
end

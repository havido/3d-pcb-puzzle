// A sweep of everything the Design tab lets you do. Each test is one scenario a user
// would actually perform; the document in localStorage is the source of truth for
// assertions, so a test fails when the *state* is wrong, not just the pixels.
import { expect, test } from '@playwright/test'

const canvas = '.design-canvas'
const doc = (page) => page.evaluate(() => JSON.parse(localStorage.getItem('design.doc.v1')))
const traces = async (page) => (await doc(page)).objects.filter((o) => o.kind === 'trace')
const holes = async (page) => (await doc(page)).objects.filter((o) => o.kind === 'hole')

async function openDesign(page) {
  await page.goto('/')
  await page.evaluate(() => localStorage.removeItem('design.doc.v1'))
  await page.reload()
  await page.getByRole('button', { name: 'Design', exact: true }).click()
  await expect(page.locator(canvas)).toBeVisible()
}

async function mmToPx(page, [mx, my]) {
  const box = await page.locator(`${canvas} svg`).boundingBox()
  const [minX, minY, w, h] = (await page.locator(`${canvas} svg`).getAttribute('viewBox')).split(/\s+/).map(Number)
  return { x: box.x + ((mx - minX) / w) * box.width, y: box.y + ((my - minY) / h) * box.height }
}
async function clickMm(page, mm, options = {}) {
  const p = await mmToPx(page, mm); await page.mouse.click(p.x, p.y, options)
}
async function dragMm(page, from, to) {
  const a = await mmToPx(page, from), b = await mmToPx(page, to)
  await page.mouse.move(a.x, a.y); await page.mouse.down(); await page.mouse.move(b.x, b.y, { steps: 8 }); await page.mouse.up()
}
async function drawTrace(page, points, { net, width } = {}) {
  await page.getByRole('button', { name: 'Trace' }).click()
  if (net) await page.locator('.net-list button', { hasText: net }).click()
  if (width) await page.locator('.width-field input').fill(String(width))
  for (const p of points) await clickMm(page, p)
  await page.keyboard.press('Enter')
}

// ---------------------------------------------------------------- outline ----

test('outline: drawing one replaces the outline and keeps the objects', async ({ page }) => {
  await openDesign(page)
  await drawTrace(page, [[30, 30], [70, 30]])
  const before = (await doc(page)).outline.points.length
  await page.getByRole('button', { name: 'Outline' }).click()
  for (const p of [[10, 10], [120, 10], [120, 80], [10, 80]]) await clickMm(page, p)
  await page.keyboard.press('Enter')
  const d = await doc(page)
  expect(d.outline.points).toHaveLength(4)
  expect(before).not.toBe(0)
  expect(d.objects.filter((o) => o.kind === 'trace')).toHaveLength(1)   // the trace survives
})

test('outline: switching tool mid-draw keeps the previous outline', async ({ page }) => {
  await openDesign(page)
  const before = (await doc(page)).outline.points
  await page.getByRole('button', { name: 'Outline' }).click()
  await clickMm(page, [20, 20])
  await clickMm(page, [90, 20])
  await page.getByRole('button', { name: 'Select' }).click()
  const after = (await doc(page)).outline.points
  expect(after).toEqual(before)                                         // nothing was destroyed
  await expect(page.locator(`${canvas} svg polygon`)).toHaveCount(1)     // and it is still drawn
})

test('outline: two points and Enter is refused, not committed', async ({ page }) => {
  await openDesign(page)
  const before = (await doc(page)).outline.points
  await page.getByRole('button', { name: 'Outline' }).click()
  await clickMm(page, [20, 20])
  await clickMm(page, [90, 20])
  await page.keyboard.press('Enter')
  expect((await doc(page)).outline.points).toEqual(before)
})

test('outline: a new outline is brought into view', async ({ page }) => {
  await openDesign(page)
  await page.getByRole('button', { name: 'Outline' }).click()
  for (const p of [[300, 300], [380, 300], [380, 360], [300, 360]]) await clickMm(page, p)
  await page.keyboard.press('Enter')
  const inView = await page.evaluate(() => {
    const svg = document.querySelector('.design-canvas svg')
    const [minX, minY, w, h] = svg.getAttribute('viewBox').split(/\s+/).map(Number)
    const pts = svg.querySelector('polygon').getAttribute('points').split(' ').map((p) => p.split(',').map(Number))
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1])
    return Math.min(...xs) < minX + w && Math.max(...xs) > minX && Math.min(...ys) < minY + h && Math.max(...ys) > minY
  })
  expect(inView).toBe(true)
})

test('outline: a preset keeps the objects', async ({ page }) => {
  await openDesign(page)
  await drawTrace(page, [[30, 30], [70, 30]])
  await page.getByRole('button', { name: 'Circle' }).click()
  expect(await traces(page)).toHaveLength(1)
  expect((await doc(page)).outline.points.length).toBeGreaterThan(8)
})

// ------------------------------------------------------------------ nets ----

test('nets: a new trace takes the selected net', async ({ page }) => {
  await openDesign(page)
  await drawTrace(page, [[20, 20], [80, 20]], { net: 'GOAL_1' })
  expect((await traces(page))[0].net).toBe('GOAL_1')
})

test('nets: each net has its own colour, and traces are drawn in it', async ({ page }) => {
  await openDesign(page)
  await drawTrace(page, [[20, 20], [80, 20]], { net: 'GOAL_1' })
  await drawTrace(page, [[20, 60], [80, 60]], { net: 'GOAL_2' })
  const strokes = await page.locator(`${canvas} svg polyline`).evaluateAll((els) => els.map((e) => e.getAttribute('stroke')))
  const unique = [...new Set(strokes)]
  expect(unique.length).toBeGreaterThan(1)
})

test('nets: changing the net in the inspector updates the trace', async ({ page }) => {
  await openDesign(page)
  await drawTrace(page, [[20, 20], [80, 20]], { net: 'GOAL_1' })
  await page.getByRole('button', { name: 'Select' }).click()
  await clickMm(page, [50, 20])
  await page.locator('.inspector-fields select').selectOption('GOAL_2')
  expect((await traces(page))[0].net).toBe('GOAL_2')
})

test('nets: clicking a net swatch with a trace selected re-assigns it', async ({ page }) => {
  await openDesign(page)
  await drawTrace(page, [[20, 20], [80, 20]], { net: 'GOAL_1' })
  await page.getByRole('button', { name: 'Select' }).click()
  await clickMm(page, [50, 20])
  await page.locator('.net-list button', { hasText: 'GOAL_2' }).click()
  expect((await traces(page))[0].net).toBe('GOAL_2')
})

test('nets: a hole takes the selected net too', async ({ page }) => {
  await openDesign(page)
  await page.locator('.net-list button', { hasText: 'GND' }).click()
  await page.getByRole('button', { name: 'Hole' }).click()
  await clickMm(page, [40, 40])
  expect((await holes(page))[0].net).toBe('GND')
})

// ---------------------------------------------------------------- editing ----

test('editing: Escape cancels a draft', async ({ page }) => {
  await openDesign(page)
  await page.getByRole('button', { name: 'Trace' }).click()
  await clickMm(page, [20, 20]); await clickMm(page, [60, 20])
  await page.keyboard.press('Escape')
  await expect(page.locator(`${canvas} svg circle`)).toHaveCount(0)
  expect(await traces(page)).toHaveLength(0)
})

test('editing: clicking empty space deselects', async ({ page }) => {
  await openDesign(page)
  await drawTrace(page, [[20, 20], [80, 20]])
  await page.getByRole('button', { name: 'Select' }).click()
  await clickMm(page, [50, 20])
  await expect(page.locator('.inspector-fields')).toBeVisible()
  await clickMm(page, [50, 90])
  await expect(page.locator('.design-right')).toContainText('Nothing selected')
})

test('editing: alt-click on a segment adds a point', async ({ page }) => {
  await openDesign(page)
  await drawTrace(page, [[20, 20], [80, 20]])
  await page.getByRole('button', { name: 'Select' }).click()
  await clickMm(page, [50, 20])
  await page.keyboard.down('Alt')
  await clickMm(page, [50, 20])
  await page.keyboard.up('Alt')
  expect((await traces(page))[0].points).toHaveLength(3)
})

test('editing: Backspace deletes the selection and undo brings it back', async ({ page }) => {
  await openDesign(page)
  await drawTrace(page, [[20, 20], [80, 20]])
  await page.getByRole('button', { name: 'Select' }).click()
  await clickMm(page, [50, 20])
  await page.keyboard.press('Backspace')
  expect(await traces(page)).toHaveLength(0)
  await page.getByRole('button', { name: /Undo/ }).click()
  expect(await traces(page)).toHaveLength(1)
})

test('editing: a hole can be selected, resized and deleted', async ({ page }) => {
  await openDesign(page)
  await page.getByRole('button', { name: 'Hole' }).click()
  await clickMm(page, [40, 40])
  await page.getByRole('button', { name: 'Select' }).click()
  await clickMm(page, [40, 40])
  await expect(page.locator('.design-right')).toContainText('Diameter')
  await page.locator('.inspector-fields input[type=number]').fill('3')
  expect((await holes(page))[0].d).toBe(3)
  await page.locator(canvas).click({ position: { x: 5, y: 5 } })   // move focus off the field
  await clickMm(page, [40, 40])
  await page.keyboard.press('Backspace')
  expect(await holes(page)).toHaveLength(0)
})

// ------------------------------------------------------------------ rules ----

test('rules: a thin trace is flagged and clears when widened', async ({ page }) => {
  await openDesign(page)
  await drawTrace(page, [[20, 20], [80, 20]], { width: 1 })
  await expect(page.locator('.rule-list li')).toHaveCount(1)
  await page.getByRole('button', { name: 'Select' }).click()
  await clickMm(page, [50, 20])
  await page.locator('.inspector-fields input[type=number]').fill('3')
  await expect(page.locator('.rule-list li')).toHaveCount(0)
})

test('rules: clicking a violation selects the object it belongs to', async ({ page }) => {
  await openDesign(page)
  await drawTrace(page, [[20, 20], [80, 20]], { width: 1 })
  await page.locator('.rule-list li').first().click()
  await expect(page.locator('.design-right')).toContainText('Width')
})

// ------------------------------------------------------- persistence + tabs ----

test('the document survives a reload and a tab switch', async ({ page }) => {
  await openDesign(page)
  await drawTrace(page, [[20, 20], [80, 20]], { net: 'GOAL_1' })
  await page.getByRole('button', { name: 'Convert', exact: true }).click()
  await page.getByRole('button', { name: 'Design', exact: true }).click()
  expect(await traces(page)).toHaveLength(1)
  await page.reload()
  await page.getByRole('button', { name: 'Design', exact: true }).click()
  expect((await traces(page))[0].net).toBe('GOAL_1')
})

test('undo history covers several edits in a row', async ({ page }) => {
  await openDesign(page)
  await drawTrace(page, [[20, 20], [80, 20]])
  await drawTrace(page, [[20, 50], [80, 50]])
  await page.getByRole('button', { name: 'Hole' }).click()
  await clickMm(page, [40, 70])
  expect((await doc(page)).objects).toHaveLength(3)
  for (let i = 0; i < 3; i++) await page.getByRole('button', { name: /Undo/ }).click()
  expect((await doc(page)).objects).toHaveLength(0)
  for (let i = 0; i < 3; i++) await page.getByRole('button', { name: /Redo/ }).click()
  expect((await doc(page)).objects).toHaveLength(3)
})

test('editing: clearing a number field must not write a zero into the board', async ({ page }) => {
  await openDesign(page)
  await drawTrace(page, [[20, 20], [80, 20]])
  await page.getByRole('button', { name: 'Select' }).click()
  await clickMm(page, [50, 20])
  await page.locator('.inspector-fields input[type=number]').fill('')     // mid-edit, field empty
  expect((await traces(page))[0].width).toBeGreaterThan(0)
})

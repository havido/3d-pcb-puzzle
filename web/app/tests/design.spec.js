// End-to-end checks for the Design tab, driven through a real browser.
// Canvas work is done in millimetres, so each test converts mm to page pixels
// through the SVG's viewBox rather than guessing at coordinates.
import { expect, test } from '@playwright/test'

const canvas = '.design-canvas'

async function openDesign(page) {
  await page.goto('/')
  await page.evaluate(() => localStorage.removeItem('design.doc.v1'))
  await page.reload()
  await page.getByRole('button', { name: 'Design', exact: true }).click()
  await expect(page.locator(canvas)).toBeVisible()
}

/** Page-pixel position of a millimetre point, from the live viewBox. */
async function mmToPx(page, [mx, my]) {
  const box = await page.locator(`${canvas} svg`).boundingBox()
  const vb = await page.locator(`${canvas} svg`).getAttribute('viewBox')
  const [minX, minY, w, h] = vb.split(/\s+/).map(Number)
  return { x: box.x + ((mx - minX) / w) * box.width, y: box.y + ((my - minY) / h) * box.height }
}

async function clickMm(page, mm, options = {}) {
  const p = await mmToPx(page, mm)
  await page.mouse.click(p.x, p.y, options)
}

async function dragMm(page, from, to) {
  const a = await mmToPx(page, from)
  const b = await mmToPx(page, to)
  await page.mouse.move(a.x, a.y)
  await page.mouse.down()
  await page.mouse.move(b.x, b.y, { steps: 8 })
  await page.mouse.up()
}

const doc = (page) => page.evaluate(() => JSON.parse(localStorage.getItem('design.doc.v1')))
const traces = async (page) => (await doc(page)).objects.filter((o) => o.kind === 'trace')

test('the Convert tab still works and the tabs switch', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('button', { name: /Goose v3/ })).toBeVisible()
  await page.getByRole('button', { name: 'Design', exact: true }).click()
  await expect(page.locator(canvas)).toBeVisible()
  await page.getByRole('button', { name: 'Convert', exact: true }).click()
  await expect(page.locator(canvas)).toHaveCount(0)
})

test('draw a trace: three clicks and Enter make exactly one trace', async ({ page }) => {
  await openDesign(page)
  await page.getByRole('button', { name: 'Trace' }).click()
  await clickMm(page, [20, 20])
  await clickMm(page, [60, 20])
  await clickMm(page, [60, 60])
  await page.keyboard.press('Enter')
  await expect(page.locator('.design-mid .dim')).toContainText('1 object')
  const t = await traces(page)
  expect(t).toHaveLength(1)
  expect(t[0].points).toHaveLength(3)
})

test('switching tools clears a half-drawn trace', async ({ page }) => {
  await openDesign(page)
  await page.getByRole('button', { name: 'Trace' }).click()
  await clickMm(page, [20, 20])
  await clickMm(page, [50, 20])
  await expect(page.locator(`${canvas} svg circle`)).toHaveCount(2)      // the draft's points
  await page.getByRole('button', { name: 'Select' }).click()
  await expect(page.locator(`${canvas} svg circle`)).toHaveCount(0)      // draft is gone
  expect(await traces(page)).toHaveLength(0)                             // and was not committed
})

test('double-click finishes a trace without adding stray points', async ({ page }) => {
  await openDesign(page)
  await page.getByRole('button', { name: 'Trace' }).click()
  await clickMm(page, [20, 30])
  await clickMm(page, [60, 30])
  const p = await mmToPx(page, [60, 70])
  await page.mouse.dblclick(p.x, p.y)
  const t = await traces(page)
  expect(t).toHaveLength(1)
  expect(t[0].points.length).toBeLessThanOrEqual(3)
})

test('a trace can be selected and moved as a whole', async ({ page }) => {
  await openDesign(page)
  await page.getByRole('button', { name: 'Trace' }).click()
  await clickMm(page, [20, 20])
  await clickMm(page, [80, 20])
  await page.keyboard.press('Enter')
  await page.getByRole('button', { name: 'Select' }).click()
  await clickMm(page, [50, 20])                                          // select it
  await expect(page.locator(`${canvas} svg rect`).first()).toBeVisible()  // vertex handles
  const before = (await traces(page))[0]
  await dragMm(page, [50, 20], [50, 45])                                 // drag the body
  const after = (await traces(page))[0]
  expect(after.points).toHaveLength(before.points.length)                // moved, not re-shaped
  expect(after.points[0][1]).toBeGreaterThan(before.points[0][1] + 15)
})

test('a vertex can be dragged', async ({ page }) => {
  await openDesign(page)
  await page.getByRole('button', { name: 'Trace' }).click()
  await clickMm(page, [20, 20])
  await clickMm(page, [80, 20])
  await page.keyboard.press('Enter')
  await page.getByRole('button', { name: 'Select' }).click()
  await clickMm(page, [50, 20])
  await dragMm(page, [80, 20], [80, 60])
  const t = (await traces(page))[0]
  expect(t.points[1][1]).toBeGreaterThan(50)
  expect(t.points[0][1]).toBeCloseTo(20, 0)                              // the other end stayed
})

test('undo and redo', async ({ page }) => {
  await openDesign(page)
  await page.getByRole('button', { name: 'Trace' }).click()
  await clickMm(page, [20, 20])
  await clickMm(page, [60, 20])
  await page.keyboard.press('Enter')
  await expect(page.locator('.design-mid .dim')).toContainText('1 object')
  await page.getByRole('button', { name: /Undo/ }).click()
  await expect(page.locator('.design-mid .dim')).toContainText('0 objects')
  await page.getByRole('button', { name: /Redo/ }).click()
  await expect(page.locator('.design-mid .dim')).toContainText('1 object')
})

test('adding a hole puts one hole on the board', async ({ page }) => {
  await openDesign(page)
  await page.getByRole('button', { name: 'Hole' }).click()
  await clickMm(page, [40, 40])
  const d = await doc(page)
  expect(d.objects.filter((o) => o.kind === 'hole')).toHaveLength(1)
})

test('rules react to a too-thin trace', async ({ page }) => {
  await openDesign(page)
  await page.getByRole('button', { name: 'Trace' }).click()
  await page.locator('.width-field input').fill('1')
  await clickMm(page, [20, 20])
  await clickMm(page, [80, 20])
  await page.keyboard.press('Enter')
  await expect(page.locator('.rule-list li').first()).toContainText('needs ≥ 3 mm')
})

test('opening the goose fills the canvas and converts to 3D', async ({ page }) => {
  test.setTimeout(60_000)
  await openDesign(page)
  await page.getByRole('button', { name: /Goose v3/ }).click()
  await expect
    .poll(async () => (await doc(page)).objects.length, { timeout: 20_000 })
    .toBeGreaterThan(4)

  // the board must actually be in view, not off-screen: its bbox overlaps the viewBox
  const inView = await page.evaluate(() => {
    const svg = document.querySelector('.design-canvas svg')
    const [minX, minY, w, h] = svg.getAttribute('viewBox').split(/\s+/).map(Number)
    const poly = svg.querySelector('polygon')
    const pts = poly.getAttribute('points').split(' ').map((p) => p.split(',').map(Number))
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1])
    return Math.min(...xs) < minX + w && Math.max(...xs) > minX &&
           Math.min(...ys) < minY + h && Math.max(...ys) > minY
  })
  expect(inView).toBe(true)

  await page.getByRole('button', { name: /Convert → 3D/ }).click()
  await expect(page.locator('.headline')).toContainText('printable board in', { timeout: 40_000 })
})

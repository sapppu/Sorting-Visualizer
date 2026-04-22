"""
Sorting Algorithm Visualizer — PRO Edition (Color TFT)
Raspberry Pi Pico / MicroPython  —  Wokwi-compatible

Controls:
  7 Algorithm buttons (GP2–GP8) — one per sort
  Reset button (GP9)           — reshuffle / abort sort
  Slide pot (GP26)             — number of blocks (6–32)
  Slide pot (GP27)             — animation speed

Hardware:
  ILI9341 320×240 TFT via SPI1 (SCK=GP10, MOSI=GP11, CS=GP13, DC=GP12, RST=GP14)
  Buzzer PWM on GP15
"""

from machine import Pin, ADC, PWM, SPI
from ili9341 import ILI9341
import utime
import random
import math

# ── Hardware init ─────────────────────────────────────────────────────────────
spi = SPI(1, baudrate=40_000_000, polarity=0, phase=0,
          sck=Pin(10), mosi=Pin(11))
tft = ILI9341(spi, cs=Pin(13, Pin.OUT), dc=Pin(12, Pin.OUT), rst=Pin(14, Pin.OUT))

btn_bubble    = Pin(2, Pin.IN, Pin.PULL_UP)
btn_insertion = Pin(3, Pin.IN, Pin.PULL_UP)
btn_selection = Pin(4, Pin.IN, Pin.PULL_UP)
btn_quick     = Pin(5, Pin.IN, Pin.PULL_UP)
btn_merge     = Pin(6, Pin.IN, Pin.PULL_UP)
btn_heap      = Pin(7, Pin.IN, Pin.PULL_UP)
btn_shell     = Pin(8, Pin.IN, Pin.PULL_UP)
btn_reset     = Pin(9, Pin.IN, Pin.PULL_UP)

pot_size  = ADC(26)
pot_speed = ADC(27)

buzzer = PWM(Pin(15))
buzzer.duty_u16(0)

# ── Colors (RGB565) ──────────────────────────────────────────────────────────
BLACK   = 0x0000
WHITE   = 0xFFFF
RED     = 0xF800
GREEN   = 0x07E0
BLUE    = 0x001F
CYAN    = 0x07FF
YELLOW  = 0xFFE0
MAGENTA = 0xF81F
ORANGE  = 0xFD20
DARK    = 0x2104
GRAY    = 0x8410

def bar_color(val):
    """Map value (1–100) to a rainbow gradient (blue→cyan→green→yellow→red)."""
    t = val / 100.0
    if t < 0.25:
        g = int(t / 0.25 * 63)
        return (0 << 11) | (g << 5) | 31
    elif t < 0.5:
        b = int((1 - (t - 0.25) / 0.25) * 31)
        return (0 << 11) | (63 << 5) | b
    elif t < 0.75:
        r = int((t - 0.5) / 0.25 * 31)
        return (r << 11) | (63 << 5) | 0
    else:
        g = int((1 - (t - 0.75) / 0.25) * 63)
        return (31 << 11) | (g << 5) | 0

# ── Layout (320×240) ─────────────────────────────────────────────────────────
SCREEN_W = 320
SCREEN_H = 240
HEADER_H = 22
FOOTER_H = 22
CHART_Y  = HEADER_H
CHART_H  = SCREEN_H - HEADER_H - FOOTER_H

MIN_N     = 6
MAX_N     = 32
MIN_DELAY = 4
MAX_DELAY = 200

ALGO_NAMES = ["BUBBLE", "INSERT", "SELECT", "QUICK", "MERGE", "HEAP", "SHELL"]
ALGO_BTNS  = [btn_bubble, btn_insertion, btn_selection,
              btn_quick, btn_merge, btn_heap, btn_shell]

arr    = []
last_n = 0

# ── ADC helpers ───────────────────────────────────────────────────────────────
def _adc_norm(adc):
    return adc.read_u16() / 65535.0

def get_n():
    return MIN_N + int(_adc_norm(pot_size) * (MAX_N - MIN_N))

def get_delay():
    t = _adc_norm(pot_speed)
    return int(MIN_DELAY + (1.0 - t) * (MAX_DELAY - MIN_DELAY))

# ── Sound ─────────────────────────────────────────────────────────────────────
def _buzz(freq, duty=20000):
    buzzer.freq(max(20, min(freq, 20000)))
    buzzer.duty_u16(duty)

def tone_compare(val):
    _buzz(150 + int(val * 8))

def tone_swap():
    _buzz(1200, 30000)

def tone_done_sweep(i, n):
    _buzz(300 + int((i / n) * 1500), 15000)

def silence():
    buzzer.duty_u16(0)

# ── Array ─────────────────────────────────────────────────────────────────────
def _shuffle(a):
    for i in range(len(a) - 1, 0, -1):
        j = random.getrandbits(8) % (i + 1)
        a[i], a[j] = a[j], a[i]

def gen_array(n=None):
    if n is None: n = get_n()
    n = max(MIN_N, min(MAX_N, n))
    a = list(range(10, 10 + n))
    _shuffle(a)
    return [int(1 + (v - 10) / max(1, n - 1) * 99) for v in a]

# ── Display helpers ───────────────────────────────────────────────────────────
def _bar_x(i, n):
    bw = max(2, SCREEN_W // n)
    return i * bw, bw

def draw_header(text_str, color=CYAN):
    tft.fill_rect(0, 0, SCREEN_W, HEADER_H, DARK)
    tft.hline(0, HEADER_H - 1, SCREEN_W, GRAY)
    tft.text(text_str[:20], 4, 3, color, DARK, 2)

def draw_footer(text_str, color=WHITE):
    tft.fill_rect(0, SCREEN_H - FOOTER_H, SCREEN_W, FOOTER_H, DARK)
    tft.hline(0, SCREEN_H - FOOTER_H, SCREEN_W, GRAY)
    tft.text(text_str[:20], 4, SCREEN_H - FOOTER_H + 3, color, DARK, 2)

def draw_bars(a, hi1=-1, hi2=-1, hi3=-1, header="", footer=""):
    tft.fill_rect(0, CHART_Y, SCREEN_W, CHART_H, BLACK)
    n = len(a)
    for i, v in enumerate(a):
        bh = max(2, int(v / 100 * CHART_H))
        x, bw = _bar_x(i, n)
        y = SCREEN_H - FOOTER_H - bh
        gap = 1 if bw > 3 else 0
        if i == hi1:
            tft.fill_rect(x + gap, y, bw - gap * 2, bh, WHITE)
        elif i == hi2:
            tft.fill_rect(x + gap, y, bw - gap * 2, bh, YELLOW)
        elif i == hi3:
            tft.fill_rect(x + gap, y, bw - gap * 2, bh, MAGENTA)
        else:
            tft.fill_rect(x + gap, y, bw - gap * 2, bh, bar_color(v))
    if header:
        draw_header(header)
    if footer:
        draw_footer(footer)
    tft.show()

def draw_done_sweep(a, title="DONE"):
    n = len(a)
    for i in range(n):
        if btn_reset.value() == 0: break
        v = a[i]
        bh = max(2, int(v / 100 * CHART_H))
        x, bw = _bar_x(i, n)
        y = SCREEN_H - FOOTER_H - bh
        gap = 1 if bw > 3 else 0
        tft.fill_rect(x + gap, y, bw - gap * 2, bh, GREEN)
        tft.show()
        tone_done_sweep(i, n)
        utime.sleep_ms(18)
        silence()
    draw_header(title, GREEN)

def show_idle():
    tft.fill_rect(0, CHART_Y, SCREEN_W, CHART_H, BLACK)
    n = len(arr)
    for i, v in enumerate(arr):
        bh = max(2, int(v / 100 * CHART_H))
        x, bw = _bar_x(i, n)
        y = SCREEN_H - FOOTER_H - bh
        gap = 1 if bw > 3 else 0
        tft.fill_rect(x + gap, y, bw - gap * 2, bh, bar_color(v))
    draw_header("SORT VIZ PRO", CYAN)
    n_now = get_n()
    d_now = get_delay()
    draw_footer(f"N={n_now:2d}  DLY={d_now:3d}ms")
    tft.show()

# ── Sort engine ───────────────────────────────────────────────────────────────
class SortStats:
    __slots__ = ("cmp", "swp", "t0")
    def __init__(self):
        self.cmp = 0; self.swp = 0; self.t0 = utime.ticks_ms()
    def footer(self):
        elapsed = utime.ticks_diff(utime.ticks_ms(), self.t0) // 1000
        return f"C:{self.cmp} S:{self.swp} {elapsed}s"

def make_callbacks(stats, algo_name):
    def compare(i, j):
        stats.cmp += 1
        tone_compare(arr[i])
        draw_bars(arr, hi1=i, hi2=j,
                  header=f"{algo_name} n={len(arr)}",
                  footer=stats.footer())
        utime.sleep_ms(get_delay())
        silence()
        return arr[i] > arr[j]
    def swap(i, j):
        if i == j: return
        arr[i], arr[j] = arr[j], arr[i]
        stats.swp += 1
        tone_swap()
        draw_bars(arr, hi1=i, hi2=j,
                  header=f"{algo_name} n={len(arr)}",
                  footer=stats.footer())
        utime.sleep_ms(max(8, get_delay() // 3))
        silence()
    def aborted():
        return btn_reset.value() == 0
    return compare, swap, aborted

def run_sort(algo_fn, algo_name):
    stats = SortStats()
    compare, swap, aborted = make_callbacks(stats, algo_name)
    algo_fn(compare, swap, aborted)
    if not aborted():
        draw_done_sweep(arr, title="SORTED!")
        draw_bars(arr, header="SORTED!",
                  footer=f"C:{stats.cmp} S:{stats.swp}")
        t = utime.ticks_ms()
        while utime.ticks_diff(utime.ticks_ms(), t) < 3000:
            if btn_reset.value() == 0: break
            if any(b.value() == 0 for b in ALGO_BTNS): break
            utime.sleep_ms(50)

# ── Sorting algorithms ────────────────────────────────────────────────────────
def bubble(compare, swap, aborted):
    n = len(arr)
    for i in range(n):
        swapped = False
        for j in range(n - i - 1):
            if aborted(): return
            if compare(j, j + 1):
                swap(j, j + 1); swapped = True
        if not swapped: break

def insertion(compare, swap, aborted):
    for i in range(1, len(arr)):
        j = i
        while j > 0:
            if aborted(): return
            if compare(j - 1, j):
                swap(j - 1, j); j -= 1
            else: break

def selection(compare, swap, aborted):
    n = len(arr)
    for i in range(n):
        min_i = i
        for j in range(i + 1, n):
            if aborted(): return
            compare(min_i, j)
            if arr[j] < arr[min_i]: min_i = j
        if min_i != i: swap(i, min_i)

def quick(compare, swap, aborted):
    def _partition(lo, hi):
        mid = (lo + hi) // 2
        if arr[mid] < arr[lo]: swap(lo, mid)
        if arr[hi] < arr[lo]:  swap(lo, hi)
        if arr[mid] < arr[hi]: swap(mid, hi)
        pivot_val = arr[hi]; i = lo - 1
        for j in range(lo, hi):
            if aborted(): return lo
            compare(j, hi)
            if arr[j] <= pivot_val:
                i += 1; swap(i, j)
        swap(i + 1, hi); return i + 1
    def _quick(lo, hi):
        if aborted(): return
        if lo < hi:
            p = _partition(lo, hi)
            _quick(lo, p - 1); _quick(p + 1, hi)
    _quick(0, len(arr) - 1)

def merge(compare, swap, aborted):
    n = len(arr); width = 1
    while width < n:
        for lo in range(0, n, 2 * width):
            mid = min(lo + width, n); hi = min(lo + 2 * width, n)
            i = lo; j = mid
            while i < j and j < hi:
                if aborted(): return
                compare(i, j)
                if arr[i] <= arr[j]: i += 1
                else:
                    tmp = arr[j]
                    for k in range(j, i, -1): arr[k] = arr[k - 1]
                    arr[i] = tmp; i += 1; j += 1
                    swap(i - 1, j - 1)
        width *= 2

def heap(compare, swap, aborted):
    n = len(arr)
    def heapify(size, root):
        largest = root; l = 2*root+1; r = 2*root+2
        if l < size:
            compare(largest, l)
            if arr[l] > arr[largest]: largest = l
        if r < size:
            compare(largest, r)
            if arr[r] > arr[largest]: largest = r
        if largest != root:
            swap(root, largest)
            if not aborted(): heapify(size, largest)
    for i in range(n//2-1, -1, -1):
        if aborted(): return
        heapify(n, i)
    for i in range(n-1, 0, -1):
        if aborted(): return
        swap(0, i); heapify(i, 0)

def shell(compare, swap, aborted):
    n = len(arr)
    for gap in [701, 301, 132, 57, 23, 10, 4, 1]:
        if gap >= n: continue
        for i in range(gap, n):
            j = i
            while j >= gap:
                if aborted(): return
                if compare(j-gap, j):
                    swap(j-gap, j); j -= gap
                else: break

ALGO_FNS = [bubble, insertion, selection, quick, merge, heap, shell]

# ── Button debounce ───────────────────────────────────────────────────────────
_press_times = {}
DEBOUNCE_MS  = 400

def button_pressed(pin):
    now = utime.ticks_ms(); pid = id(pin)
    if pin.value() == 0:
        last = _press_times.get(pid, 0)
        if utime.ticks_diff(now, last) > DEBOUNCE_MS:
            _press_times[pid] = now; return True
    return False

# ── Startup splash ────────────────────────────────────────────────────────────
def splash():
    tft.fill(BLACK)
    tft.text("SORT VIZ PRO", 40, 60, CYAN, BLACK, 3)
    tft.text("PRESS A BUTTON", 30, 120, WHITE, BLACK, 2)
    tft.text("TO START SORTING!", 20, 150, GRAY, BLACK, 2)
    tft.text("SLIDE TO SET N & SPEED", 4, 190, YELLOW, BLACK, 2)
    tft.show()
    utime.sleep_ms(2000)

# ── Main ──────────────────────────────────────────────────────────────────────
splash()
arr    = gen_array()
last_n = len(arr)

while True:
    n_now = get_n()
    if n_now != last_n:
        last_n = n_now
        arr = gen_array(n_now)
    show_idle()
    for i in range(len(ALGO_BTNS)):
        if button_pressed(ALGO_BTNS[i]):
            arr = gen_array(n_now)
            run_sort(ALGO_FNS[i], ALGO_NAMES[i])
            while any(b.value() == 0 for b in ALGO_BTNS) or btn_reset.value() == 0:
                utime.sleep_ms(50)
            break
    if button_pressed(btn_reset):
        arr = gen_array(n_now)
    utime.sleep_ms(60)
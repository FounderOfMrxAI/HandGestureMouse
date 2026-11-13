#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
El Hareketleriyle Bilgisayar Kontrolü
=====================================
Web kamerası + MediaPipe Hand Landmarker ile tek eli takip eder; el hareketlerini
fare hareketi, sol/sağ tık ve sayfa kaydırmaya çevirir.

----------------------------------------------------------------------------
KURULUM
----------------------------------------------------------------------------
1) Paketler (Python 3.9 - 3.12 önerilir):

       pip install opencv-python mediapipe pyautogui numpy

   Linux'ta ayrıca Tkinter gerekir:  sudo apt install python3-tk python3-dev
   macOS'ta: Sistem Ayarları > Gizlilik ve Güvenlik altında Terminal/IDE'ye
   "Erişilebilirlik" ve "Kamera" izni verin (aksi halde fare kontrol edilemez).

2) MediaPipe model dosyası (hand_landmarker.task) - main.py ile AYNI klasöre indirin:

   Windows (PowerShell):
       Invoke-WebRequest -Uri "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task" -OutFile hand_landmarker.task

   Linux / macOS (curl):
       curl -L -o hand_landmarker.task https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task

   Linux (wget):
       wget -O hand_landmarker.task https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task

3) Çalıştırma:   python main.py

----------------------------------------------------------------------------
JESTLER  (öncelik: Scroll(yumruk) > Sol tık > Sağ tık > Mouse hareketi)
----------------------------------------------------------------------------
 MOVE        : Baş parmak + İŞARET parmağı birleştir (tutup) ve elini hareket
               ettir -> imleç elinle birlikte gider. (Referans: landmark 9)
 LEFT CLICK  : Baş parmak + ORTA parmak değer (tek tık, basılı tutunca tekrarlamaz).
 RIGHT CLICK : Baş parmak + YÜZÜK parmağı değer.
 SCROLL      : Eli KAPAT (yumruk: dört parmak da kapalı). Yumruk halindeyken el dikey
               hareket -> yukarı/aşağı, yatay hareket -> sağa/sola kaydırma.
               (Tık yapmak için en az bir parmağın açık kalması gerekir, yoksa yumruk sayılır.)

Tüm kamera görüntüsü okunur ve (varsayılan olarak) tüm kamera alanı tüm ekrana
eşlenir. Çıkış: ESC (overlay odaktayken), overlay'e fare ile tıklama veya Ctrl+C.

----------------------------------------------------------------------------
PERFORMANS MİMARİSİ
----------------------------------------------------------------------------
 Thread 1 (kamera)   : sürekli kare okur, her zaman en son kareyi tutar (eski kareler atılır)
 Thread 2 (işleme)   : MediaPipe + jest mantığı + fare/scroll eylemleri + önizleme çizimi
 Ana thread (Tkinter): sadece hazır önizlemeyi ekrana basar
 Böylece kamera beklemesi, el algılama ve pencere çizimi birbirini yavaşlatmaz.
"""

import sys
import os
import time
import math
import base64
import platform
import threading
from dataclasses import dataclass


# ============================================================================
# CONFIG - Tüm ayarlar burada. Mesafe eşikleri "el boyutuna" (bilek[0] ile
# orta parmak MCP[9] arası mesafe) bölünmüş değerlerdir; yani kameraya
# yakın/uzak olmanız sonucu değiştirmez.
# ============================================================================
CONFIG = {
    # --- Kamera / Model ---------------------------------------------------
    "CAMERA_INDEX": 0,              # Kamera numarası (0 = varsayılan kamera)
    "CAMERA_WIDTH": 640,            # İstenen kamera genişliği (piksel)
    "CAMERA_HEIGHT": 480,           # İstenen kamera yüksekliği (piksel)
    "CAMERA_FPS": 30,               # İstenen kamera FPS değeri
    "CAMERA_FOURCC": "MJPG",        # MJPG çoğu USB kamerada FPS'i ciddi artırır. Sorun olursa "" yapın
    "DETECT_WIDTH": 320,            # El algılama için görüntü genişliği. Küçük = hızlı (kamera 640 kalır,
                                    # tüm kare okunur, sadece algılama için küçültülür). 320-480 arası deneyin
    "MODEL_PATH": os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "hand_landmarker.task"),  # Model dosyası yolu
    "DETECT_CONF": 0.6,             # El algılama güven eşiği (0-1)
    "PRESENCE_CONF": 0.5,           # El varlığı güven eşiği (0-1)
    "TRACK_CONF": 0.5,              # Takip güven eşiği (0-1)

    # --- Parmak "uzatılmış mı?" kararı (bilgi amaçlı; jestler artık yumruk ölçüsünü kullanır) ---
    "FINGER_EXTEND_RATIO": 1.15,

    # --- Baş parmak "hangi parmağa dokunuyor?" kararı -----------------------
    # Baş parmak ucuna en yakın parmak (işaret/orta/yüzük) bir sonrakinden en az
    # bu kadar yakın olmalı; belirsizse (iki parmağa eşit yakınsa) jest sayılmaz.
    "PINCH_MARGIN": 0.06,

    # --- Jest 1: MOUSE HAREKETİ (baş parmak + işaret parmak birleşik) ------
    "MOVE_PINCH_ON": 0.30,          # Bu mesafenin ALTINDA "birleşti" sayılır
    "MOVE_PINCH_OFF": 0.42,         # Hareket jestinden çıkmak için aşılması gereken mesafe (histerezis)
    "ACTIVE_REGION_X": 1.0,         # Kamera genişliğinin ne kadarı ekranın tamamına eşlenir (1.0 = tam kamera)
    "ACTIVE_REGION_Y": 1.0,         # Kamera yüksekliğinin ne kadarı ekranın tamamına eşlenir
                                    # (kenarlara ulaşmak zor gelirse 0.8-0.9 yapın)
    "MOVE_SENSITIVITY": 2.5,        # Hassasiyet çarpanı: el aynı mesafe hareket edince imleç bu kadar kat fazla gider.
                                    # Etkin alan = ACTIVE_REGION / MOVE_SENSITIVITY (2.5 -> kameranın ortadaki %40'ı
                                    # tüm ekranı kapsar). 1.0 = eski davranış, 3-4 = daha da hassas
    "MOVE_SMOOTHING": 0.30,         # EMA katsayısı (0-1). Küçük = daha yumuşak ama gecikmeli
                                    # (hassasiyet arttıkça titreme de büyür; titrerse 0.2-0.25 yapın)
    "MOVE_DEADZONE_PX": 3,          # Bu pikselden küçük imleç hareketleri yok sayılır (titreme)

    # --- Jest 2: SOL TIK (baş parmak + orta parmak) ------------------------
    "LEFT_CLICK_ON": 0.28,          # Bu mesafenin ALTINDA "değiyor" sayılır
    "LEFT_CLICK_OFF": 0.40,         # Tık jesti bozulması için aşılması gereken mesafe (histerezis)

    # --- Jest 3: SAĞ TIK (baş parmak + yüzük parmağı) ----------------------
    # Yanlış sağ tıkları azaltmak için eşik daha sıkı, onay süresi daha uzun (CONFIRM_MS).
    "RIGHT_CLICK_ON": 0.22,         # Bu mesafenin ALTINDA "değiyor" sayılır (sol tıktan daha sıkı)
    "RIGHT_CLICK_OFF": 0.34,        # Jestten çıkma eşiği (histerezis)
    "RIGHT_CLICK_MARGIN": 0.10,     # Yüzük parmağı, diğer parmaklardan en az bu kadar daha yakın olmalı

    # --- Jest 4: SCROLL (yumruk: el kapalı) --------------------------------
    # Yumruk ölçüsü = dört parmak ucunun bileğe uzaklığının (el boyuna oranla) en büyüğü.
    # Parmaklar kapanınca bu değer küçülür (açık el ~1.8-2.0, yumruk ~0.6-1.0).
    "SCROLL_FIST_ON": 1.05,         # Bu değerin ALTINDA yumruk sayılır. Yumruk algılanmıyorsa büyütün (1.2)
    "SCROLL_FIST_OFF": 1.25,        # Yumruktan çıkma eşiği (histerezis)
    "SCROLL_SMOOTHING": 0.50,       # Scroll için EMA katsayısı (0-1)
    "SCROLL_DEADZONE": 0.0015,      # Kare başına bu kadar (kare oranı) altındaki hareket yok sayılır
    "SCROLL_GAIN": 0.50,            # Hız çarpanı: %1 kare/kare hareket başına kaç "tekerlek çentiği"
    "SCROLL_EXPONENT": 1.3,         # 1.0 = doğrusal; >1 hızlı harekette ivmelenir, yavaşta hassas olur
    "SCROLL_MAX_NOTCH_PER_FRAME": 6.0,  # Kare başına en fazla çentik (güvenlik sınırı)
    "SCROLL_AXIS_LOCK": True,       # True: aynı anda sadece baskın eksende kaydır
    "SCROLL_INVERT_Y": False,       # True: dikey yönü ters çevir
    "SCROLL_INVERT_X": False,       # True: yatay yönü ters çevir
    # pyautogui.scroll birimi işletim sistemine göre değişir (Windows'ta 120 = 1 çentik).
    "SCROLL_UNIT": {"Windows": 120, "Darwin": 1, "Linux": 1},

    # --- Onay süresi (ms): jest bu kadar kesintisiz sürmezse tetiklenmez ---
    "CONFIRM_MS": {
        "LEFT CLICK": 250,
        "RIGHT CLICK": 450,         # Sağ tık için daha uzun bekleme (yanlış tetiklemeyi önler)
        "SCROLL": 150,
        "MOVE": 100,
    },
    "RELEASE_MS": 60,               # Jestin bittiğine karar vermek için gereken süre (anlık titreşim filtresi)
    "CLICK_COOLDOWN_MS": 400,       # İki tık arası en az bekleme

    # --- Overlay (önizleme penceresi) --------------------------------------
    "OVERLAY_WIDTH": 320,           # Pencere genişliği (yükseklik orana göre hesaplanır)
    "OVERLAY_FPS": 30,              # Önizlemenin en fazla kaç kez/sn yenileneceği
    "OVERLAY_MARGIN_RIGHT": 16,     # Ekranın sağ kenarından boşluk
    "OVERLAY_MARGIN_BOTTOM": 64,    # Alt kenardan boşluk (görev çubuğunu kapatmasın diye)
    "OVERLAY_ALPHA": 0.88,          # Şeffaflık (1.0 = opak). Linux'ta compositor gerekir
    "OVERLAY_BORDERLESS": True,     # True: çerçevesiz. ESC çalışmazsa False yapın
    "SHOW_ACTIVE_REGION": True,     # Çalışma alanı < 1.0 ise önizlemede dikdörtgenini çiz
}

# ----------------------------------------------------------------------------
# Jest isimleri
# ----------------------------------------------------------------------------
G_NOHAND = "NO HAND"
G_IDLE = "IDLE"
G_MOVE = "MOVE"
G_LEFT = "LEFT CLICK"
G_RIGHT = "RIGHT CLICK"
G_SCROLL = "SCROLL"
CLICK_GESTURES = (G_LEFT, G_RIGHT)

GESTURE_COLORS = {  # BGR
    G_NOHAND: (160, 160, 160),
    G_IDLE: (220, 220, 220),
    G_MOVE: (80, 220, 80),
    G_LEFT: (60, 90, 255),
    G_RIGHT: (255, 80, 220),
    G_SCROLL: (255, 200, 40),
}

# MediaPipe el landmark indeksleri
WRIST = 0
THUMB_TIP = 4
INDEX_PIP, INDEX_TIP = 6, 8
MIDDLE_PIP, MIDDLE_TIP = 10, 12
RING_PIP, RING_TIP = 14, 16
PINKY_PIP, PINKY_TIP = 18, 20
REF_POINT = 9  # Referans: orta parmak MCP (landmark 9)

HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12), (9, 13), (13, 14), (14, 15),
    (15, 16), (13, 17), (17, 18), (18, 19), (19, 20), (0, 17),
]


# ============================================================================
# Bağımlılık kontrolü (anlaşılır Türkçe hata mesajlarıyla)
# ============================================================================
def fatal(message):
    """Hata mesajını yazdırıp programdan çıkar."""
    print("\n[HATA] " + message + "\n", file=sys.stderr)
    sys.exit(1)


def _import_or_die(module_name, pip_name):
    try:
        return __import__(module_name)
    except ImportError:
        fatal(f"'{module_name}' paketi bulunamadı.\n"
              f"        Kurmak için:  pip install {pip_name}")


np = _import_or_die("numpy", "numpy")
cv2 = _import_or_die("cv2", "opencv-python")
pyautogui = _import_or_die("pyautogui", "pyautogui")
mp = _import_or_die("mediapipe", "mediapipe")

try:
    from mediapipe.tasks import python as mp_tasks
    from mediapipe.tasks.python import vision as mp_vision
except ImportError:
    fatal("Kurulu MediaPipe sürümü 'Tasks' (HandLandmarker) API'sini içermiyor.\n"
          "        Güncellemek için:  pip install --upgrade mediapipe")

try:
    import tkinter as tk
except ImportError:
    fatal("Tkinter bulunamadı (overlay penceresi için gerekli).\n"
          "        Linux'ta:  sudo apt install python3-tk")

# PyAutoGUI ayarları: köşeye gidince durdurma (fail-safe) kapatılır çünkü
# ekran köşelerine gitmek normal kullanımın parçasıdır. Her çağrı sonrası bekleme yok.
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0
try:
    pyautogui.MINIMUM_DURATION = 0
except Exception:
    pass


# ============================================================================
# Yardımcı sınıf ve fonksiyonlar
# ============================================================================
def dist(a, b):
    """İki nokta arası Öklid mesafesi."""
    return float(math.hypot(a[0] - b[0], a[1] - b[1]))


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def effective_region():
    """Hassasiyet çarpanı uygulandıktan sonra ekranın tamamına eşlenen kamera alanı (oran, x ve y)."""
    sens = max(CONFIG["MOVE_SENSITIVITY"], 1e-3)
    return (min(1.0, CONFIG["ACTIVE_REGION_X"] / sens),
            min(1.0, CONFIG["ACTIVE_REGION_Y"] / sens))


class EMA2D:
    """2B nokta için üstel hareketli ortalama (low-pass) filtresi."""

    def __init__(self, alpha):
        self.alpha = alpha
        self.value = None

    def update(self, point):
        p = np.array(point, dtype=float)
        if self.value is None:
            self.value = p
        else:
            self.value = self.alpha * p + (1.0 - self.alpha) * self.value
        return self.value

    def reset(self):
        self.value = None


@dataclass
class HandFeatures:
    """Bir kare için hesaplanmış el özellikleri (tüm mesafeler el boyutuna normalize)."""
    pts: object              # (21, 2) piksel koordinatları
    ref: tuple               # Referans nokta (landmark 9), 0-1 normalize kamera koordinatı
    size: float              # El boyutu: mesafe(bilek, landmark 9) piksel
    index_ext: bool
    middle_ext: bool
    ring_ext: bool
    pinky_ext: bool
    d_thumb_index: float
    d_thumb_middle: float
    d_thumb_ring: float
    d_index_middle: float
    fist_metric: float       # Dört parmak ucunun bileğe uzaklığının en büyüğü / el boyu (küçük = yumruk)


def compute_features(pts_norm, width, height):
    """Normalize landmark'lardan jest özelliklerini çıkarır."""
    pts = pts_norm * np.array([width, height], dtype=float)
    size = max(dist(pts[WRIST], pts[REF_POINT]), 1e-6)
    ratio = CONFIG["FINGER_EXTEND_RATIO"]

    def extended(tip, pip):
        return dist(pts[tip], pts[WRIST]) > dist(pts[pip], pts[WRIST]) * ratio

    return HandFeatures(
        pts=pts,
        ref=(float(pts_norm[REF_POINT][0]), float(pts_norm[REF_POINT][1])),
        size=size,
        index_ext=extended(INDEX_TIP, INDEX_PIP),
        middle_ext=extended(MIDDLE_TIP, MIDDLE_PIP),
        ring_ext=extended(RING_TIP, RING_PIP),
        pinky_ext=extended(PINKY_TIP, PINKY_PIP),
        d_thumb_index=dist(pts[THUMB_TIP], pts[INDEX_TIP]) / size,
        d_thumb_middle=dist(pts[THUMB_TIP], pts[MIDDLE_TIP]) / size,
        d_thumb_ring=dist(pts[THUMB_TIP], pts[RING_TIP]) / size,
        d_index_middle=dist(pts[INDEX_TIP], pts[MIDDLE_TIP]) / size,
        fist_metric=max(dist(pts[t], pts[WRIST]) for t in (INDEX_TIP, MIDDLE_TIP, RING_TIP, PINKY_TIP)) / size,
    )


def thumb_target(f, margin=None):
    """
    Baş parmak ucuna en yakın parmağı ('index' / 'middle' / 'ring') ve mesafesini döndürür.
    En yakın parmak, ikinci en yakından PINCH_MARGIN kadar yakın değilse belirsizdir -> (None, mesafe).
    Böylece baş parmak iki parmağa birden yakınken yanlışlıkla tık/hareket tetiklenmez.
    """
    items = sorted([("index", f.d_thumb_index), ("middle", f.d_thumb_middle), ("ring", f.d_thumb_ring)],
                   key=lambda kv: kv[1])
    (name, d1), (_, d2) = items[0], items[1]
    if d2 - d1 < (CONFIG["PINCH_MARGIN"] if margin is None else margin):
        return None, d1
    return name, d1


# ============================================================================
# JEST ALGILAMA FONKSİYONLARI
# was_active: jest bir önceki karede de aktifse histerezis uygulanır (titreşimi önler)
# ============================================================================
def detect_move(f, was_active=False):
    """Baş parmak + işaret parmak birleşik mi? (imleci hareket ettirme modu)"""
    thr = CONFIG["MOVE_PINCH_OFF"] if was_active else CONFIG["MOVE_PINCH_ON"]
    name, d = thumb_target(f)
    return name == "index" and d < thr


def detect_left_click(f, was_active=False):
    """Baş parmak + orta parmak değiyor mu?"""
    thr = CONFIG["LEFT_CLICK_OFF"] if was_active else CONFIG["LEFT_CLICK_ON"]
    name, d = thumb_target(f)
    return name == "middle" and d < thr


def detect_right_click(f, was_active=False):
    """Baş parmak + yüzük parmağı değiyor mu?"""
    thr = CONFIG["RIGHT_CLICK_OFF"] if was_active else CONFIG["RIGHT_CLICK_ON"]
    name, d = thumb_target(f, CONFIG["RIGHT_CLICK_MARGIN"])
    return name == "ring" and d < thr


def detect_scroll(f, was_active=False):
    """El kapalı mı? (yumruk: dört parmak ucu da avuca yakın)"""
    thr = CONFIG["SCROLL_FIST_OFF"] if was_active else CONFIG["SCROLL_FIST_ON"]
    return f.fist_metric < thr


def resolve_gesture(f, prev_gesture):
    """
    Öncelik: Scroll(yumruk) > Sol tık > Sağ tık > Mouse hareketi > Boşta.
    Yumruk en katı poz olduğu için başa alındı: yumrukta baş parmak parmaklara değdiğinden
    sırası sonda olsaydı sürekli yanlış tık algılanırdı.
    """
    if detect_scroll(f, prev_gesture == G_SCROLL):
        return G_SCROLL
    if detect_left_click(f, prev_gesture == G_LEFT):
        return G_LEFT
    if detect_right_click(f, prev_gesture == G_RIGHT):
        return G_RIGHT
    if detect_move(f, prev_gesture == G_MOVE):
        return G_MOVE
    return G_IDLE


# ============================================================================
# Onay süresi + cooldown yöneten durum makinesi
# ============================================================================
class GestureTracker:
    """
    Ham (kare bazlı) jestleri "onaylı" jeste çevirir:
      - Bir jest, CONFIRM_MS boyunca kesintisiz sürerse onaylanır.
      - Tık jestleri onaylandığında BİR kez tetiklenir; jest bozulana kadar tekrarlanmaz.
      - İki tık arasında en az CLICK_COOLDOWN_MS beklenir.
    """

    def __init__(self):
        self.stable = G_IDLE
        self.candidate = None
        self.candidate_since = 0.0
        self.pending_fire = False
        self.last_click_t = -1e9

    def reset(self):
        self.stable = G_IDLE
        self.candidate = None
        self.pending_fire = False

    def update(self, raw, now):
        """Onaylı jesti günceller. Tık tetiklenecekse G_LEFT / G_RIGHT döndürür."""
        if raw == self.stable:
            self.candidate = None
        else:
            if raw != self.candidate:
                self.candidate = raw
                self.candidate_since = now
            need_ms = CONFIG["RELEASE_MS"] if raw == G_IDLE else CONFIG["CONFIRM_MS"].get(raw, 100)
            if (now - self.candidate_since) * 1000.0 >= need_ms:
                self.stable = raw
                self.candidate = None
                if raw in CLICK_GESTURES:
                    self.pending_fire = True  # Yalnızca jest ilk onaylandığında

        fire = None
        if self.pending_fire:
            if self.stable not in CLICK_GESTURES:
                self.pending_fire = False
            elif (now - self.last_click_t) * 1000.0 >= CONFIG["CLICK_COOLDOWN_MS"]:
                fire = self.stable
                self.pending_fire = False
                self.last_click_t = now
        return fire


# ============================================================================
# Kamera iş parçacığı: her zaman EN SON kareyi tutar (birikme/gecikme olmaz)
# ============================================================================
class CameraThread(threading.Thread):
    def __init__(self, cap):
        super().__init__(daemon=True)
        self.cap = cap
        self.cond = threading.Condition()
        self.frame = None
        self.fid = 0
        self.dead = False
        self.stopped = False
        self.fps = 0.0

    def run(self):
        failures = 0
        last_t = time.perf_counter()
        while not self.stopped:
            ok, frame = self.cap.read()
            if not ok:
                failures += 1
                if failures > 100:
                    with self.cond:
                        self.dead = True
                        self.cond.notify_all()
                    return
                time.sleep(0.01)
                continue
            failures = 0
            now = time.perf_counter()
            dt = now - last_t
            last_t = now
            if dt > 0:
                inst = 1.0 / dt
                self.fps = inst if self.fps == 0 else 0.9 * self.fps + 0.1 * inst
            with self.cond:
                self.frame = frame
                self.fid += 1
                self.cond.notify_all()

    def wait_latest(self, last_id, timeout=0.5):
        """Yeni bir kare gelene kadar bekler; (kare, id) döndürür. Zaman aşımında (None, last_id)."""
        with self.cond:
            self.cond.wait_for(
                lambda: (self.frame is not None and self.fid != last_id) or self.stopped or self.dead,
                timeout)
            if self.frame is None or self.fid == last_id:
                return None, last_id
            return self.frame, self.fid

    def stop(self):
        self.stopped = True
        with self.cond:
            self.cond.notify_all()


# ============================================================================
# Overlay çizimi
# ============================================================================
def render_preview(frame, pts_norm, label, pending, fps, cam_fps):
    """Kamera karesi + landmark + jest adı + FPS içeren küçük önizleme görüntüsü üretir (frame üzerine çizer)."""
    h, w = frame.shape[:2]
    ow = CONFIG["OVERLAY_WIDTH"]
    oh = int(h * ow / w)
    img = frame if ow == w else cv2.resize(frame, (ow, oh), interpolation=cv2.INTER_AREA)

    mx, my = effective_region()
    if CONFIG["SHOW_ACTIVE_REGION"] and (mx < 0.999 or my < 0.999):
        p1 = (int((1 - mx) / 2 * ow), int((1 - my) / 2 * oh))
        p2 = (int((1 + mx) / 2 * ow), int((1 + my) / 2 * oh))
        cv2.rectangle(img, p1, p2, (120, 200, 255), 1)  # Bu kutu = tüm ekranı kapsayan alan

    color = GESTURE_COLORS.get(label, (255, 255, 255))
    if pts_norm is not None:
        px = [(int(x * ow), int(y * oh)) for x, y in pts_norm]
        for a, b in HAND_CONNECTIONS:
            cv2.line(img, px[a], px[b], color, 2, cv2.LINE_AA)
        for i, p in enumerate(px):
            cv2.circle(img, p, 4 if i in (THUMB_TIP, INDEX_TIP, MIDDLE_TIP, RING_TIP, PINKY_TIP) else 3,
                       (255, 255, 255), -1, cv2.LINE_AA)
        cv2.circle(img, px[REF_POINT], 6, color, 2, cv2.LINE_AA)  # Referans nokta

    # Üst şerit: jest adı (sol) + FPS (sağ)
    cv2.rectangle(img, (0, 0), (ow, 30), (0, 0, 0), -1)
    cv2.putText(img, label, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2, cv2.LINE_AA)
    fps_txt = f"{fps:4.1f} FPS  (cam {cam_fps:2.0f})"
    (tw, _), _ = cv2.getTextSize(fps_txt, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)
    cv2.putText(img, fps_txt, (ow - tw - 8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.42,
                (200, 200, 200), 1, cv2.LINE_AA)

    # Onay bekleyen jest (henüz tetiklenmedi)
    if pending and pending != label:
        cv2.putText(img, f"... {pending}", (8, oh - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    GESTURE_COLORS.get(pending, (255, 255, 255)), 1, cv2.LINE_AA)
    return img


class Overlay:
    """Sağ alt köşede, her zaman üstte duran küçük (yarı saydam) önizleme penceresi."""

    def __init__(self, on_close, is_synthetic_click):
        self.on_close = on_close
        self.is_synthetic_click = is_synthetic_click
        self.root = tk.Tk()
        self.root.title("El Hareketi Kontrol")
        if CONFIG["OVERLAY_BORDERLESS"]:
            self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-alpha", CONFIG["OVERLAY_ALPHA"])
        except tk.TclError:
            pass  # Şeffaflık desteklenmiyor; sorun değil

        w = CONFIG["OVERLAY_WIDTH"]
        h = int(CONFIG["CAMERA_HEIGHT"] * w / CONFIG["CAMERA_WIDTH"])
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x = sw - w - CONFIG["OVERLAY_MARGIN_RIGHT"]
        y = sh - h - CONFIG["OVERLAY_MARGIN_BOTTOM"]
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        self.label = tk.Label(self.root, bd=0, highlightthickness=0, bg="black")
        self.label.pack(fill="both", expand=True)
        self.label.bind("<Button-1>", self._on_click)
        self.root.bind_all("<Escape>", lambda e: self.on_close())
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(300, self._grab_focus)
        self._photo = None
        self._png_mode = False  # PPM çalışmazsa PNG'ye düşülür

    def _grab_focus(self):
        try:
            self.root.focus_force()  # Çerçevesiz pencerede ESC alabilmek için
        except tk.TclError:
            pass

    def _on_click(self, _event):
        # Programın kendi ürettiği tıklamalar (imleç overlay üstündeyken) kapatmasın.
        if self.is_synthetic_click():
            return
        self.on_close()

    def show(self, bgr_image):
        h, w = bgr_image.shape[:2]
        if not self._png_mode:
            try:
                # PPM: PNG'den çok daha hızlı (sıkıştırma/base64 yok)
                rgb = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2RGB)
                data = b"P6 %d %d 255 " % (w, h) + rgb.tobytes()
                photo = tk.PhotoImage(data=data, format="PPM")
                self.label.configure(image=photo)
                self._photo = photo
                return
            except tk.TclError:
                self._png_mode = True
        ok, buf = cv2.imencode(".png", bgr_image, [cv2.IMWRITE_PNG_COMPRESSION, 1])
        if ok:
            photo = tk.PhotoImage(data=base64.b64encode(buf.tobytes()))
            self.label.configure(image=photo)
            self._photo = photo


# ============================================================================
# Ana uygulama
# ============================================================================
class GestureControlApp:
    def __init__(self):
        self.screen_w, self.screen_h = pyautogui.size()
        self.system = platform.system()
        self.running = True
        self.error = None

        self.landmarker = self._create_landmarker()
        self.cap = self._open_camera()
        self.camera = CameraThread(self.cap)

        self.tracker = GestureTracker()
        self.move_ema = EMA2D(CONFIG["MOVE_SMOOTHING"])
        self.scroll_ema = EMA2D(CONFIG["SCROLL_SMOOTHING"])
        self.last_raw = G_IDLE
        self.cursor = None            # Son bilinen imleç konumu (float)
        self.prev_scroll = None
        self.acc_x = 0.0
        self.acc_y = 0.0
        self.last_synth_click_t = -1e9
        self.last_ts_ms = 0
        self.fps = 0.0
        self.last_proc_t = time.perf_counter()

        self.preview = None
        self.preview_id = 0
        self.shown_id = 0
        self.preview_lock = threading.Lock()

        self.worker = threading.Thread(target=self._worker, daemon=True)
        self.overlay = Overlay(self.stop, self._recent_synthetic_click)

    # ---------------------------------------------------------------- kurulum
    def _create_landmarker(self):
        path = CONFIG["MODEL_PATH"]
        if not os.path.isfile(path):
            fatal(f"Model dosyası bulunamadı: {path}\n"
                  "        'hand_landmarker.task' dosyasını main.py ile aynı klasöre indirin.\n"
                  "        İndirme komutları için dosyanın en üstündeki açıklamalara bakın.")
        if os.path.getsize(path) < 1_000_000:
            fatal(f"Model dosyası bozuk veya eksik görünüyor ({path}).\n"
                  "        Dosyayı silip yeniden indirin.")
        try:
            # Dosyayı Python ile okuyup bellekten veriyoruz: MediaPipe'ın C++ katmanı
            # Windows'ta ASCII olmayan yolları (ö, ü, ş, ı...) açamıyor.
            with open(path, "rb") as fh:
                model_bytes = fh.read()
            options = mp_vision.HandLandmarkerOptions(
                base_options=mp_tasks.BaseOptions(model_asset_buffer=model_bytes),
                running_mode=mp_vision.RunningMode.VIDEO,
                num_hands=1,
                min_hand_detection_confidence=CONFIG["DETECT_CONF"],
                min_hand_presence_confidence=CONFIG["PRESENCE_CONF"],
                min_tracking_confidence=CONFIG["TRACK_CONF"],
            )
            return mp_vision.HandLandmarker.create_from_options(options)
        except Exception as exc:
            fatal(f"MediaPipe modeli yüklenemedi: {exc}\n"
                  "        Model dosyasının doğru ve eksiksiz indirildiğinden emin olun.")

    def _open_camera(self):
        idx = CONFIG["CAMERA_INDEX"]
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW) if self.system == "Windows" else cv2.VideoCapture(idx)
        if not cap.isOpened():
            cap.release()
            fatal(f"Web kamerası açılamadı (CAMERA_INDEX={idx}).\n"
                  "        Kameranın bağlı olduğunu, başka bir program tarafından kullanılmadığını\n"
                  "        ve izinlerin verildiğini kontrol edin; gerekirse CONFIG'te CAMERA_INDEX'i değiştirin.")
        fourcc = CONFIG["CAMERA_FOURCC"]
        if fourcc:  # Çözünürlükten ÖNCE ayarlanmalı
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, CONFIG["CAMERA_WIDTH"])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CONFIG["CAMERA_HEIGHT"])
        cap.set(cv2.CAP_PROP_FPS, CONFIG["CAMERA_FPS"])
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Eski kareler birikmesin
        except Exception:
            pass
        ok, _ = cap.read()
        if not ok:
            cap.release()
            fatal("Kameradan görüntü alınamıyor. Kamera başka bir uygulamada açık olabilir.")
        print(f"Kamera: {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))} "
              f"@ {cap.get(cv2.CAP_PROP_FPS):.0f} FPS (istenen)")
        return cap

    # ----------------------------------------------------------------- yardımcı
    def _recent_synthetic_click(self):
        return (time.perf_counter() - self.last_synth_click_t) < 0.6

    def stop(self):
        self.running = False
        try:
            self.overlay.root.quit()
        except Exception:
            pass

    def _map_to_screen(self, nx, ny):
        """Kamera (0-1) koordinatını ekran pikseline çevirir; çalışma alanı tüm ekrana yayılır."""
        mx, my = effective_region()
        ux = clamp((nx - (1 - mx) / 2) / mx, 0.0, 1.0)   # Kenarlarda durur (clamp)
        uy = clamp((ny - (1 - my) / 2) / my, 0.0, 1.0)
        return ux * (self.screen_w - 1), uy * (self.screen_h - 1)

    # ---------------------------------------------------------- eylemler
    def do_click(self, which):
        self.last_synth_click_t = time.perf_counter()
        if which == G_LEFT:
            pyautogui.click()
        elif which == G_RIGHT:
            pyautogui.rightClick()

    def do_move(self, smoothed_ref):
        tx, ty = self._map_to_screen(smoothed_ref[0], smoothed_ref[1])
        if self.cursor is not None and math.hypot(tx - self.cursor[0], ty - self.cursor[1]) < CONFIG["MOVE_DEADZONE_PX"]:
            return
        self.cursor = (tx, ty)
        pyautogui.moveTo(int(tx), int(ty), _pause=False)

    @staticmethod
    def _speed_to_notch(d):
        """Kare başına hareket miktarını (kare oranı) tekerlek çentiğine çevirir."""
        a = abs(d)
        dz = CONFIG["SCROLL_DEADZONE"]
        if a < dz:
            return 0.0
        u = (a - dz) / 0.01                                  # %1'lik birimlere çevir
        n = CONFIG["SCROLL_GAIN"] * (u ** CONFIG["SCROLL_EXPONENT"])
        return math.copysign(min(n, CONFIG["SCROLL_MAX_NOTCH_PER_FRAME"]), d)

    def do_scroll(self, smoothed_ref):
        if self.prev_scroll is None:
            self.prev_scroll = smoothed_ref.copy()
            return
        dx = float(smoothed_ref[0] - self.prev_scroll[0])
        dy = float(smoothed_ref[1] - self.prev_scroll[1])
        self.prev_scroll = smoothed_ref.copy()

        if CONFIG["SCROLL_AXIS_LOCK"]:            # Sadece baskın eksen
            if abs(dx) > abs(dy):
                dy = 0.0
            else:
                dx = 0.0

        # El yukarı (dy<0) -> yukarı scroll (+). El sağa (dx>0) -> sağa scroll (+).
        ny = -self._speed_to_notch(dy) * (-1 if CONFIG["SCROLL_INVERT_Y"] else 1)
        nx = self._speed_to_notch(dx) * (-1 if CONFIG["SCROLL_INVERT_X"] else 1)
        self.acc_y += ny
        self.acc_x += nx

        unit = CONFIG["SCROLL_UNIT"].get(self.system, 1)
        vy = int(self.acc_y * unit)               # Kesirli kalanı biriktir -> akıcı kaydırma
        if vy:
            pyautogui.scroll(vy)
            self.acc_y -= vy / unit
        vx = int(self.acc_x * unit)
        if vx:
            try:
                pyautogui.hscroll(vx)
            except (AttributeError, NotImplementedError):
                pyautogui.keyDown("shift")
                pyautogui.scroll(-vx)
                pyautogui.keyUp("shift")
            self.acc_x -= vx / unit

    # ------------------------------------------------------------- işleme
    def _handle_hand(self, feats, now):
        raw = resolve_gesture(feats, self.last_raw)
        self.last_raw = raw
        move_ref = self.move_ema.update(feats.ref)
        scroll_ref = self.scroll_ema.update(feats.ref)

        fire = self.tracker.update(raw, now)
        if fire:
            self.do_click(fire)

        stable = self.tracker.stable
        # Eylem yalnızca jest hem onaylıysa HEM DE o an hâlâ sürüyorsa yapılır.
        if stable == G_MOVE and raw == G_MOVE:
            self.do_move(move_ref)
        if stable == G_SCROLL and raw == G_SCROLL:
            self.do_scroll(scroll_ref)
        else:
            self.prev_scroll = None
            self.acc_x = self.acc_y = 0.0
        return stable

    def _handle_no_hand(self):
        """El kayboldu: kontrol tamamen durur, tüm durumlar sıfırlanır."""
        self.tracker.reset()
        self.last_raw = G_IDLE
        self.move_ema.reset()
        self.scroll_ema.reset()
        self.prev_scroll = None
        self.acc_x = self.acc_y = 0.0
        return G_NOHAND

    def _worker(self):
        """İşleme iş parçacığı: en son kareyi alır, el algılar, eylemleri yapar, önizlemeyi hazırlar."""
        last_id = -1
        dw = CONFIG["DETECT_WIDTH"]
        try:
            while self.running:
                frame, fid = self.camera.wait_latest(last_id, 0.5)
                if self.camera.dead:
                    raise RuntimeError("Kameradan görüntü alınamıyor; kamera bağlantısı kopmuş olabilir.")
                if frame is None:
                    continue
                last_id = fid
                now = time.perf_counter()

                # TAM kare kullanılır; sadece algılama hızı için küçültülür (kırpma yok).
                h0, w0 = frame.shape[:2]
                if dw < w0:
                    small = cv2.resize(frame, (dw, int(h0 * dw / w0)), interpolation=cv2.INTER_AREA)
                else:
                    small = frame
                small = cv2.flip(small, 1)  # Ayna görüntüsü: sağa hareket = imleç sağa
                h, w = small.shape[:2]
                rgb = np.ascontiguousarray(cv2.cvtColor(small, cv2.COLOR_BGR2RGB))
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                ts = max(int(now * 1000), self.last_ts_ms + 1)  # Zaman damgası artan olmalı
                self.last_ts_ms = ts
                result = self.landmarker.detect_for_video(mp_image, ts)

                pts_norm = None
                if result.hand_landmarks:
                    pts_norm = np.array([[p.x, p.y] for p in result.hand_landmarks[0]], dtype=float)
                    feats = compute_features(pts_norm, w, h)
                    label = self._handle_hand(feats, now)
                else:
                    label = self._handle_no_hand()

                # İşleme FPS'i (üstel ortalama)
                t = time.perf_counter()
                dt = t - self.last_proc_t
                self.last_proc_t = t
                if dt > 0:
                    inst = 1.0 / dt
                    self.fps = inst if self.fps == 0 else 0.9 * self.fps + 0.1 * inst

                pending = self.tracker.candidate if pts_norm is not None else None
                img = render_preview(small, pts_norm, label, pending, self.fps, self.camera.fps)
                with self.preview_lock:
                    self.preview = img
                    self.preview_id += 1
        except Exception as exc:  # Beklenmeyen hata: ana thread'e bildir, temiz kapan
            self.error = f"Beklenmeyen hata: {exc}"
            self.running = False

    # ------------------------------------------------------------- arayüz
    def _ui_tick(self):
        """Ana (Tkinter) thread: sadece hazır önizlemeyi ekrana basar."""
        if self.error:
            print(f"\n[HATA] {self.error}", file=sys.stderr)
            self.stop()
            return
        if not self.running:
            return
        img = None
        with self.preview_lock:
            if self.preview_id != self.shown_id:
                img = self.preview
                self.shown_id = self.preview_id
        if img is not None:
            self.overlay.show(img)
        self.overlay.root.after(max(1, int(1000 / CONFIG["OVERLAY_FPS"])), self._ui_tick)

    def run(self):
        print("El hareketi kontrolü başladı. Çıkmak için ESC, overlay'e tıklama veya Ctrl+C.")
        self.camera.start()
        self.worker.start()
        self.overlay.root.after(10, self._ui_tick)
        try:
            self.overlay.root.mainloop()
        except KeyboardInterrupt:
            pass
        finally:
            self.cleanup()

    def cleanup(self):
        self.running = False
        self.camera.stop()
        self.worker.join(timeout=2.0)
        self.camera.join(timeout=2.0)
        try:
            self.cap.release()
        except Exception:
            pass
        try:
            self.landmarker.close()
        except Exception:
            pass
        try:
            self.overlay.root.destroy()
        except Exception:
            pass
        print("Program kapatıldı.")


def _enable_windows_dpi_awareness():
    """Windows'ta ekran ölçeklemesi yüzünden imleç/overlay koordinatlarının kaymasını önler."""
    if platform.system() != "Windows":
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def main():
    _enable_windows_dpi_awareness()
    try:
        app = GestureControlApp()
    except tk.TclError as exc:
        fatal(f"Pencere oluşturulamadı (ekran/ortam sorunu): {exc}")
    app.run()


if __name__ == "__main__":
    main()

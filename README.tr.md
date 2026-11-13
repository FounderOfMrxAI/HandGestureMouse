# ✋ HandGestureMouse

**Bilgisayarını sadece web kamerasıyla el hareketlerinle kontrol et.**
English: [README.md](README.md)

HandGestureMouse, web kameranla tek elini [MediaPipe Hand Landmarker](https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker) ile takip eder ve el hareketlerini fare hareketine, sol/sağ tıka ve sayfa kaydırmaya çevirir. Özel bir donanım gerekmez.

## ✨ Özellikler

- 🖱️ Elinle **fare hareketi**
- 👆 Parmak birleştirerek **sol tık / sağ tık**
- 📜 Yumrukla **dikey ve yatay kaydırma**
- ⚡ **Çok iş parçacıklı mimari** (kamera, işleme ve arayüz ayrı thread'lerde) sayesinde düşük gecikme
- 🎛️ **Tamamen ayarlanabilir** — tüm eşikler, hassasiyet ve yumuşatma değerleri `main.py` başındaki `CONFIG` sözlüğünde
- 🪟 Algılanan eli ve güncel jesti gösteren küçük, yarı saydam **önizleme penceresi**
- 🧠 Mesafe eşikleri el boyutuna göre normalize edilir; kameraya yakın ya da uzak olman sonucu değiştirmez
- 💻 Windows, Linux ve macOS desteği

## 🤚 Jestler

| Eylem | Jest |
|---|---|
| **İmleci hareket ettir** | **Baş parmak + işaret parmağını** birleştir ve elini hareket ettir |
| **Sol tık** | **Baş parmak + orta parmağı** değdir |
| **Sağ tık** | **Baş parmak + yüzük parmağını** değdir |
| **Kaydırma (scroll)** | Elini **yumruk** yap, sonra yukarı/aşağı/sağa/sola hareket ettir |

Jestler çakışırsa öncelik: `Scroll (yumruk) > Sol tık > Sağ tık > Fare hareketi`.
Tık yapmak için en az bir parmağın açık kalması gerekir, aksi halde el yumruk sayılır.

## 📦 Kurulum

**Gereksinimler:** Python 3.9 – 3.12 ve bir web kamerası.

```bash
git clone https://github.com/<kullanici-adin>/HandGestureMouse.git
cd HandGestureMouse
pip install -r requirements.txt
```

**Sadece Linux:** `sudo apt install python3-tk python3-dev`
**Sadece macOS:** *Sistem Ayarları → Gizlilik ve Güvenlik* altında Terminal/IDE'ye *Kamera* ve *Erişilebilirlik* izni ver.

### Model dosyası

`hand_landmarker.task` dosyası `main.py` ile **aynı klasörde** olmalıdır. Repoda yoksa indir:

```bash
# Linux / macOS
curl -L -o hand_landmarker.task https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task
```

```powershell
# Windows (PowerShell)
Invoke-WebRequest -Uri "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task" -OutFile hand_landmarker.task
```

## ▶️ Kullanım

```bash
python main.py
```

Çıkmak için: **ESC** (önizleme penceresi odaktayken), önizleme penceresine tıkla veya terminalde **Ctrl+C**.

## ⚙️ Ayarlar

`main.py` dosyasını aç ve `CONFIG` sözlüğünü düzenle. Sık kullanılanlar:

| Ayar | Ne yapar |
|---|---|
| `CAMERA_INDEX` | Kullanılacak kamera (0 = varsayılan) |
| `MOVE_SENSITIVITY` | Yükseldikçe aynı el hareketinde imleç daha çok gider |
| `MOVE_SMOOTHING` | Düştükçe imleç daha yumuşak ama gecikmeli olur (titrerse 0.2–0.25 dene) |
| `SCROLL_FIST_ON` | Yumruk algılanmıyorsa büyüt (ör. 1.2) |
| `DETECT_WIDTH` | Küçüldükçe algılama hızlanır (320–480 önerilir) |
| `CAMERA_FOURCC` | MJPG kamerada sorun çıkarırsa `""` yap |
| `SCROLL_INVERT_Y` / `SCROLL_INVERT_X` | Kaydırma yönünü ters çevir |
| `OVERLAY_BORDERLESS` | ESC pencereyi kapatmazsa `False` yap |

## 🛠️ Sorun giderme

- **Kamera açılmıyor:** `CAMERA_INDEX` değerini değiştir veya kamerayı kullanan diğer uygulamaları kapat.
- **Windows'ta imleç kayıyor:** Uygulama DPI duyarlılığını otomatik açar; son sürümü kullandığından emin ol.
- **Düşük FPS:** `DETECT_WIDTH` değerini düşür, ortamı iyi aydınlat, `CAMERA_FOURCC` değerini `"MJPG"` bırak.
- **PyAutoGUI güvenlik özelliği:** İmleci ekran köşesine götürmek PyAutoGUI'yi durdurabilir. Bu bir güvenlik önlemidir.

## 🏗️ Nasıl çalışır?

1. **Kamera thread'i** sadece en son kareyi tutar (eski kareler atılır).
2. **İşleme thread'i** MediaPipe'ı çalıştırır, jestleri yorumlar (yanlış tetiklemeyi önlemek için histerezis ve onay süreleriyle) ve fare/scroll eylemlerini yapar.
3. **Ana (Tkinter) thread** sadece hazır önizlemeyi ekrana basar.

## ⚠️ Uyarı

Bu program gerçek farenizi kontrol eder. Dikkatli kullanın ve durdurmak için **Ctrl+C**'ye basabilecek şekilde klavye/fareyi yakınınızda tutun.

## 📄 Lisans

Kod [MIT Lisansı](LICENSE) ile yayımlanmıştır.
`hand_landmarker.task`, Google MediaPipe tarafından Apache 2.0 lisansıyla sunulan bir modeldir.

## 🙏 Teşekkürler

[MediaPipe](https://github.com/google-ai-edge/mediapipe) · [OpenCV](https://opencv.org/) · [PyAutoGUI](https://github.com/asweigart/pyautogui) · [NumPy](https://numpy.org/)

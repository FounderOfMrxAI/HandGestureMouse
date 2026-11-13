# ✋ HandGestureMouse

**Control your computer with hand gestures — using just a webcam.**
Türkçe için: [README.tr.md](README.tr.md)

HandGestureMouse tracks a single hand with your webcam using [MediaPipe Hand Landmarker](https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker) and turns your hand movements into mouse movement, left/right clicks and scrolling. No special hardware needed.

## ✨ Features

- 🖱️ **Mouse movement** with your hand
- 👆 **Left click / right click** with finger pinches
- 📜 **Vertical & horizontal scrolling** with a fist
- ⚡ **Multi-threaded design** (camera, processing and UI run in separate threads) for low latency
- 🎛️ **Fully configurable** — every threshold, sensitivity and smoothing value is in the `CONFIG` dictionary at the top of `main.py`
- 🪟 Small, semi-transparent **preview overlay** showing the detected hand and the current gesture
- 🧠 Distance thresholds are normalized by hand size, so it works the same whether you are near or far from the camera
- 💻 Windows, Linux and macOS support

## 🤚 Gestures

| Action | Gesture |
|---|---|
| **Move cursor** | Pinch **thumb + index finger** and move your hand |
| **Left click** | Touch **thumb + middle finger** |
| **Right click** | Touch **thumb + ring finger** |
| **Scroll** | Close your hand into a **fist**, then move it up/down/left/right |

Priority when gestures overlap: `Scroll (fist) > Left click > Right click > Mouse move`.
To click, at least one finger must stay open — otherwise the hand counts as a fist.

## 📦 Installation

**Requirements:** Python 3.9 – 3.12 and a webcam.

```bash
git clone https://github.com/<your-username>/HandGestureMouse.git
cd HandGestureMouse
pip install -r requirements.txt
```

**Linux only:** `sudo apt install python3-tk python3-dev`
**macOS only:** grant *Camera* and *Accessibility* permission to your Terminal/IDE under *System Settings → Privacy & Security*.

### Model file

`hand_landmarker.task` must be in the **same folder** as `main.py`. If it is not included in the repo, download it:

```bash
# Linux / macOS
curl -L -o hand_landmarker.task https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task
```

```powershell
# Windows (PowerShell)
Invoke-WebRequest -Uri "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task" -OutFile hand_landmarker.task
```

## ▶️ Usage

```bash
python main.py
```

To quit: press **ESC** (while the overlay is focused), click the overlay, or press **Ctrl+C** in the terminal.

## ⚙️ Configuration

Open `main.py` and edit the `CONFIG` dictionary. Common tweaks:

| Setting | What it does |
|---|---|
| `CAMERA_INDEX` | Which camera to use (0 = default) |
| `MOVE_SENSITIVITY` | Higher = cursor moves further for the same hand movement |
| `MOVE_SMOOTHING` | Lower = smoother but slower cursor (try 0.2–0.25 if it jitters) |
| `SCROLL_FIST_ON` | Raise (e.g. 1.2) if your fist is not detected |
| `DETECT_WIDTH` | Lower = faster detection (320–480 recommended) |
| `CAMERA_FOURCC` | Set to `""` if MJPG causes camera problems |
| `SCROLL_INVERT_Y` / `SCROLL_INVERT_X` | Reverse scroll direction |
| `OVERLAY_BORDERLESS` | Set to `False` if ESC does not close the window |

## 🛠️ Troubleshooting

- **Camera not opening:** change `CAMERA_INDEX`, or close other apps using the camera.
- **Cursor offset on Windows:** the app enables DPI awareness automatically; make sure you run the latest version.
- **Low FPS:** lower `DETECT_WIDTH`, make sure the room is well lit, keep `CAMERA_FOURCC` as `"MJPG"`.
- **PyAutoGUI fail-safe:** moving the cursor to a screen corner may stop PyAutoGUI. This is a safety feature.

## 🏗️ How it works

1. **Camera thread** keeps only the latest frame (old frames are dropped).
2. **Processing thread** runs MediaPipe, interprets gestures (with hysteresis and confirmation times to avoid false triggers) and performs mouse/scroll actions.
3. **Main (Tkinter) thread** only displays the ready-made preview.

## ⚠️ Disclaimer

This program controls your real mouse. Use it carefully and keep your keyboard/mouse at hand to stop it with **Ctrl+C**.

## 📄 License

The code is released under the [MIT License](LICENSE).
`hand_landmarker.task` is a model provided by Google MediaPipe under the Apache 2.0 license.

## 🙏 Acknowledgements

[MediaPipe](https://github.com/google-ai-edge/mediapipe) · [OpenCV](https://opencv.org/) · [PyAutoGUI](https://github.com/asweigart/pyautogui) · [NumPy](https://numpy.org/)

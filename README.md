# Bouncing Ball Pygame 🎮

![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

A Python implementation of a bouncing ball game using the Pygame library.

## 📜 About
This project implements a simple physics-based bouncing ball game where players control a platform to bounce a ball and prevent it from falling off the screen. It's an excellent example of basic game development principles and physics simulation in Python using Pygame.

## ✨ Features
- Physics-based ball movement with realistic bouncing
- Player-controlled platform with arrow key input
- Score tracking and level progression
- Lives system with game over conditions
- Color-changing platform for visual feedback

## 🚀 Quick Start

### Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/fahadelahikhan/Bouncing-Ball-Pygame.git
   cd Bouncing-Ball-Pygame
   ```

2. Install required dependencies:
   ```bash
   pip install pygame
   ```

3. Run the game:
   ```bash
   python main.py
   ```

### Basic Usage
```python
# The game is controlled via keyboard inputs
# Use the LEFT and RIGHT arrow keys to move the platform
# Prevent the ball from falling off the bottom of the screen
# Each successful bounce increases your score
```

### Example Game Session
```python
# The ball starts at the center of the screen with random velocity
ball_pos = [400, 300]
ball_speed = [3.0, 3.5]

# The platform starts at the bottom center of the screen
platform_pos = [350, 560]

# As the player bounces the ball, the score increases
# When the score reaches 10, the player advances to level 2
current_level = 2
```

## 📖 How It Works
The game implements basic physics principles:
- The ball moves according to its velocity vector
- When the ball hits a wall or the platform, its velocity is reflected
- The platform can be moved horizontally using arrow keys
- The game tracks score and lives, with increasing difficulty per level

## ⚖️ License
Distributed under the MIT License. See [LICENSE](LICENSE) for details.

---

> **Note**: This implementation is for educational and entertainment purposes. The game logic and physics are simplified for demonstration purposes.

## 🥔 La Patate Royale: merge game + reel maker (`potato_reel/`)

A potato merge game in two forms:

- **A video reel** (1080×1920 MP4): a bot plays a real game from an empty ring,
  aiming and dropping one potato at a time, until the last potato appears.
- **A browser game** you play yourself: touch to aim, release to drop, with an Auto mode.

Two potatoes of the same kind merge into the next, bigger one, and every merge
plays a French voice line, **« La patate … »**, pitched deeper the bigger the potato.
You lose if the pile stays above the top of the ring.

| Tier | Voice line | Tier | Voice line | Tier | Voice line |
|---|---|---|---|---|---|
| 1 | La patate Bébé | 4 | La patate Chef | 7 | La patate Ninja |
| 2 | La patate Douce | 5 | La patate Mamie | 8 | La patate Viking |
| 3 | La patate Pirate | 6 | La patate Rappeur | 9 | La patate Royale |

### Requirements
- Python 3.9+ and `ffmpeg` on your PATH
- `pip install -r requirements.txt`
- Internet access the first time (voice lines come from Google's French TTS and are cached in `output/voices/`)

### Make a reel
```bash
python -m potato_reel                       # picks a game the bot wins in 55–85s
python -m potato_reel --seed 13 --out output/reel_13.mp4
python -m potato_reel --min-len 45 --max-len 60
python -m potato_reel --hook "Wait for the last potato" --teaser "NOUVEAU : La patate Royale"
python -m potato_reel --characters          # saves output/characters.png (the whole cast)
python -m potato_reel --stills 5,20         # also saves PNG frames at those seconds
```
Every seed is a different game, so render a few and post the best one.

### Build the browser game
```bash
python -m potato_reel.web                   # writes output/potato_game.html (open it in any browser)
```
The file is self-contained (art and voices embedded), so it works offline and on a phone.

### Customising
- **Characters:** edit `CAST` in `potato_reel/characters.py` (name, skin colour, drawing style).
- **Your own voice:** put recordings in `output/voices/` named `<tier>_<Name>.mp3` or `.wav`
  (for example `9_Royale.mp3`, `1_Bebe.wav`; accents dropped from the file name). They replace the generated lines.
- **Game rules:** `Tuning` in `potato_reel/physics.py` (gravity, which potatoes you get, cooldown).
  The browser game has the same values at the top of its script in `potato_reel/web_template.html`.

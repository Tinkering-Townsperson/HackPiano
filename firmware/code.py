"""Firmware for the HackPiano.

The HackPiano is a custom MIDI keyboard made by AfterNoon PM as his HackPad project.
"""

###########
# IMPORTS #
###########

# General stuff
import board  # type: ignore
import time

# MIDI stuff
import usb_midi  # type: ignore
import adafruit_midi
from adafruit_midi.note_on import NoteOn
from adafruit_midi.note_off import NoteOff
from adafruit_midi.control_change import ControlChange  # noqa

# OLED stuff
import busio  # type: ignore
import displayio  # type: ignore
import adafruit_displayio_ssd1306
import terminalio  # type: ignore
from adafruit_display_text import label

# Keyboard/KMK stuff
from kmk.kmk_keyboard import KMKKeyboard  # type: ignore
from kmk.keys import KC, Key  # type: ignore
from kmk.scanners import DiodeOrientation  # type: ignore
from kmk.extensions.button import Button  # type: ignore


#########
# SETUP #
#########

# Constants
__version__ = "1.0.0"
VELOCITY = 127
WIDTH = 128
HEIGHT = 32
BORDER = 1

# MIDI setup
midi = adafruit_midi.MIDI(usb_midi.ports[0], out_channel=0)

# Button setup
button_pin = board.D3

# OLED setup
OLED_SDA = board.D4
OLED_SCL = board.D5
i2c = busio.I2C(OLED_SCL, OLED_SDA)
displayio.release_displays()
display_bus = displayio.I2CDisplay(i2c, device_address=0x3C)
display = adafruit_displayio_ssd1306.SSD1306(display_bus, width=128, height=32)

main_screen = displayio.Group()
display.root_group = main_screen


######################
# MIDIKEYBOARD CLASS #
######################

class MidiKeyboard(KMKKeyboard):
	def __init__(self, screen: displayio.Group, cc_default: int = 0, cc_off: int = 0, cc_on: int = 127, cc_code: int = 64):
		"""Initialize the MidiKeyboard class

		Args:
			screen (displayio.Group): Group (splash/screen) to write to.
			cc_default (int 0-127, optional): The default value of the CC. Defaults to 0.
			cc_off (int 0-127, optional): The off value of the CC. Defaults to 0.
			cc_on (int 0-127, optional): The on value of the CC. Defaults to 127.
			cc_code (int 0-127, optional): The Control Change code. Defaults to 64.
		"""
		super().__init__()
		self.row_pins = (board.D6, board.D7, board.D8, board.D10)
		self.col_pins = (board.D9, board.D0, board.D1, board.D2)
		self.diode_orientation = DiodeOrientation.COL2ROW

		# KC.N0 for custom logic. will handle later on in MidiKeyboard.process_key
		self.keymap = [
			[
				KC.NO, KC.NO, KC.NO, KC.NO,
				KC.NO, KC.NO, KC.NO, KC.NO,
				KC.NO, KC.NO, KC.NO, KC.NO,
				KC.NO, KC.NO, KC.NO, KC.NO,
			]
		]

		self.midi_note_map = {
			# Row 0
			0: 60,  # C4
			1: 61,  # C#4
			2: 62,  # D4
			3: 63,  # D#4
			# Row 1
			4: 64,  # E4
			5: 65,  # F4
			6: 66,  # F#4
			7: 67,  # G4
			# Row 2
			8: 68,  # G#4
			9: 69,  # A4
			10: 70,  # A#4
			11: 71,  # B4
		}

		self.transpose = 0
		self.control = cc_default
		self.controlchange = cc_code
		self.active_midi_notes = list()
		self.extensions.append(Button([button_pin]))
		self.screen = screen

		self.currently_playing = label.Label(
			terminalio.FONT,
			text = "",
			color = 0xFFFFFF,
			x = 3,
			y = HEIGHT // 2 - 1
		)
		self.screen.append(self.currently_playing)

		self.transposition = label.Label(
			terminalio.FONT,
			text = "",
			color = 0xFFFFFF,
			x = 72,
			y = HEIGHT // 3 - 1
		)
		self.screen.append(self.transposition)

		self.control_status = label.Label(
			terminalio.FONT,
			text = "",
			color = 0xFFFFFF,
			x = 72,
			y = (HEIGHT // 3) * 2 - 1
		)
		self.screen.append(self.control_status)

	def process_key(self, key: Key) -> None:
		"""Process a key press event.

		Keys 0-11 play a MIDI note with the current transposition setting applied. Keys 12-15 adjust the transposition setting.

		Args:
			key (Key): The key object representing the key being pressed
		"""

		if 0 <= key.key_number <= 11:
			midi_note = self.midi_note_map[key.key_number]

			if key.pressed:
				if midi_note not in self.active_midi_notes:
					midi.send(NoteOn(midi_note + self.transpose, VELOCITY))
					self.active_midi_notes.append(midi_note + self.transpose)

			else:
				if midi_note in self.active_midi_notes:
					midi.send(NoteOff(midi_note + self.transpose, 0))
					self.active_midi_notes.remove(midi_note + self.transpose)

			self.update_oled()

		elif 12 <= key.key_number <= 15:
			if key.pressed:
				print(f"Control Key SW{key.key_number + 1} Pressed")
				self.transpose += \
					-12 if key.key_number == 12 else \
					1 if key.key_number == 13 else \
					12 if key.key_number == 14 else \
					-1 if key.key_number == 15 else 0
			else:
				print(f"Control Key SW{key.key_number + 1} Released")

			self.update_oled()

		# TODO: Handle push button = toggle sustain (MIDI CC 64)

		super().process_key(key)

	def update_oled(self) -> None:
		"""Update the OLED display to show the current state of the MIDI controller.

		This function updates the display with the currently playing note, the transposition value,
		and the control status. If there are active MIDI notes, it displays the name of the last
		note played. The transposition value is shown with a '+' sign if positive, and as a plain
		number if negative or zero. The control status is displayed as a MIDI control change value.
		"""

		self.currently_playing.text = self._get_note_name(self.active_midi_notes[-1]) if len(self.active_midi_notes) > 0 else ""
		self.transposition.text = str(self.transpose) if self.transpose < 0 else f"+{self.transpose}" if self.transpose > 0 else ""
		self.control_status.text = f"CC={self.control}"

	def _get_note_name(self, note_number: int) -> str:
		"""Convert a MIDI note number to its corresponding note name.

		*For transparency, I generated this helper function using Gemini.*

		Args:
			note_number (int): Note number to be converted

		Returns:
			str: formatted note name
		"""
		note_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
		octave = (note_number // 12) - 1  # MIDI note 0 is C-1, so C4 is octave 4
		note_in_octave = note_number % 12
		return f"{note_names[note_in_octave]}{octave}"


######################
# OLED SPLASH SCREEN #
######################
def outline_screen(screen: displayio.Group) -> None:
	"""Draw a white outline around the screen with a black interior.

	Drawing a white border around the screen helps the display stand out on the
	Macropad. The black interior provides a clean background for the controls and
	text to be displayed on.

	Args:
		screen (displayio.Group): Group (splash/screen) to write to.
	"""

	color_bitmap = displayio.Bitmap(WIDTH, HEIGHT, 1)
	color_palette = displayio.Palette(1)
	color_palette[0] = 0xFFFFFF

	bg_sprite = displayio.TileGrid(color_bitmap, pixel_shader=color_palette, x=0, y=0)
	screen.append(bg_sprite)

	inner_bitmap = displayio.Bitmap(WIDTH - BORDER * 2, HEIGHT - BORDER * 2, 1)
	inner_palette = displayio.Palette(1)
	inner_palette[0] = 0x000000
	inner_sprite = displayio.TileGrid(inner_bitmap, pixel_shader=inner_palette, x=BORDER, y=BORDER)
	screen.append(inner_sprite)


def splash_screen(screen: displayio.Group, text: str) -> None:
	"""Display a splash screen with a given text.
	Animate the text in from left to right, then out again, for a typewriter effect.

	Args:
		screen (displayio.Group): Group (splash/screen) to write to.
		text (str): The text to display on the splash screen.
	"""
	text_area = label.Label(terminalio.FONT, text="", color=0xFFFFFF, x=32, y=HEIGHT // 2 - 1)
	screen.append(text_area)

	for i in range(len(text) + 1):
		text_area.text = text[0:i]
		time.sleep(0.25)

	time.sleep(2)

	for i in range(len(text) + 1):
		text_area.text = " " * i + text[i:len(text)]
		time.sleep(0.25)

	screen.remove(text_area)


#############
# MAIN LOOP #
#############

keyboard = MidiKeyboard(screen=main_screen)

if __name__ == '__main__':
	outline_screen(screen=main_screen)
	splash_screen(screen=main_screen, text=f"HackPiano v{__version__[0]}")
	keyboard.go()

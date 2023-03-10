import os
import time
import json
import busio
from datetime import datetime
from colr import color
import adafruit_tcs34725
import digitalio
import board
import adafruit_mcp3xxx.mcp3008 as MCP
from adafruit_mcp3xxx.analog_in import AnalogIn
import firebase_admin
from firebase_admin import credentials
from firebase_admin import db

import pyfiglet
f = pyfiglet.Figlet(font='slant')
print(f.renderText('Smart Pantry'))

# Initialize I2C bus and COLOR SENSOR.
i2c = busio.I2C(board.SCL, board.SDA)
sensor = adafruit_tcs34725.TCS34725(i2c)
 
sensor.integration_time = 200
sensor.gain = 60

ID_CONTENEDOR = "-LrgBqkkQGmHw_MjgcU5"  

# Fetch the service account key JSON file contents
cred = credentials.Certificate(
    'potus-65895-firebase-adminsdk-r6mjh-f1e99b2d66.json')
# Initialize the app with a service account, granting admin privileges
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://potus-65895.firebaseio.com/'
})

ref = db.reference('Config')
configuracion = ref.get()

print('# Database Setup')

# create the spi bus
spi = busio.SPI(clock=board.SCK, MISO=board.MISO, MOSI=board.MOSI)

# create the cs (chip select)
cs = digitalio.DigitalInOut(board.D22)

# create the mcp object
mcp = MCP.MCP3008(spi, cs)

# create an analog input channel on pin 0
chan0 = AnalogIn(mcp, MCP.P0)


last_read = 0       # this keeps track of the last potentiometer value
tolerance = 250     # to keep from being jittery we'll only change
# volume when the pot has moved a significant amount
# on a 16-bit ADC

print('# SPI Setup')


def remap_range(value, left_min, left_max, right_min, right_max):
    # this remaps a value from original (left) range to new (right) range
    # Figure out how 'wide' each range is
    left_span = left_max - left_min
    right_span = right_max - right_min

    # Convert the left range into a 0-1 range (int)
    valueScaled = int(value - left_min) / int(left_span)

    # Convert the 0-1 range into a value in the right range.
    return int(right_min + (valueScaled * right_span))


print('# Main Code Start')
while True:
    pantry_ref = db.reference('Containers/'+str(ID_CONTENEDOR))
    ref = db.reference('Log/'+str(ID_CONTENEDOR))
    enable_status = db.reference('Containers/'+str(ID_CONTENEDOR)+'/Status')
    led = digitalio.DigitalInOut(board.D26)
    led.direction = digitalio.Direction.OUTPUT

    led_stat = enable_status.get()

    if(led_stat == "ENABLE"):
        led.value = False
    else:
        led.value = ~led.value

    # we'll assume that the pot didn't move
    trim_pot_changed = False

    # read the analog pin
    trim_pot = chan0.value

    # how much has it changed since the last read?
    pot_adjust = abs(trim_pot - last_read)

    if pot_adjust > tolerance:
        trim_pot_changed = True

    if trim_pot_changed:
        # convert 16bit adc0 (0-65535) trim pot read into 0-100 volume level
        set_volume = remap_range(trim_pot, 0, 44224, 0, 100)

        if set_volume < configuracion["LowLimit"]:
            print('-------*Queda poco producto')
            pantry_ref.update({
                'Content': 'LowLimit',
                'Volumen': set_volume
            })

        if set_volume > configuracion["UpperLimit"]:
            print('-------*El embase esta muy lleno')
            pantry_ref.update({
                'Content': 'UpperLimit',
                'Volumen': set_volume
            })

        now = datetime.now()
        current_time = now.strftime("%m-%d-%y %H:%M:%S")

        # Generate a reference to a new location and add some data using push()
        new_log_ref = ref.push({
            'Status': set_volume,
            'Time': current_time
        })
        
        colores = sensor.color_rgb_bytes
        print('Color: ({0}, {1}, {2})'.format(*sensor.color_rgb_bytes))
        print(color('xxxxxxx', fore=(colores[0],colores[1],colores[2]), back=(0,0,0)))
        pantry_ref.update({
                'R': colores[0],
                'G': colores[1],
                'B': colores[2]
            })

        # print('ADC VALUE ' + str(trim_pot))
        # set OS volume playback volume
        print('Volumen = {volume}%' .format(volume=set_volume))
        # set_vol_cmd = 'sudo amixer cset numid=1 -- {volume}% > /dev/null' \
        # .format(volume = set_volume)
        # os.system(set_vol_cmd)

        # save the potentiometer reading for the next loop
        last_read = trim_pot

    # hang out and do nothing for a half second
    time.sleep(0.5)

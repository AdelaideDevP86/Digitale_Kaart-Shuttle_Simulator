from robot import config, hardware
import time

hardware.initialiseer(config.HARDWARE)
print("Sensortest gestart, schuif de robot met de hand. Stop met Ctrl-C.")
vorig = None
while True:
    p = hardware.lees_meting()["patroon"]
    if p != vorig:
        print(time.ticks_ms(), p)
        vorig = p
    time.sleep_ms(5)
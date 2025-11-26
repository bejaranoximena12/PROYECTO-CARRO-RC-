# ================= TX: NRF24L01 + 2 Joysticks (Servo + Motor) =================
from machine import Pin, SPI, ADC
import utime, struct
from nrf24l01 import NRF24L01

# ---- Radio SPI0 ----
spi = SPI(0, sck=Pin(6), mosi=Pin(7), miso=Pin(4))
csn = Pin(15, Pin.OUT, value=1)
ce  = Pin(14, Pin.OUT, value=0)

TX_ADDR = b'\xE1\xF0\xF0\xF0\xF0'
RX_ADDR = b'\xD2\xF0\xF0\xF0\xF0'

nrf = None  # se inicializa en iniciar_nrf()

def iniciar_nrf():
    global nrf
    try:
        nrf = NRF24L01(spi, csn, ce, payload_size=8)
        nrf.open_tx_pipe(TX_ADDR)
        nrf.open_rx_pipe(1, RX_ADDR)
        nrf.set_power_speed(3, 1)   # 0 dBm, 1 Mbps (igual que antes)
        nrf.reg_write(0x01, 0x00)   # No Auto-Ack
        nrf.reg_write(0x04, 0x00)   # Sin retransmisiones
        nrf.reg_write(0x05, 100)    # Canal 100
        nrf.stop_listening()
        print("🔄 NRF TX inicializado/reiniciado OK")
    except Exception as e:
        print("⚠ Error iniciando NRF TX:", e)
        nrf = None

iniciar_nrf()

# ---- Joysticks ----
adc_servo = ADC(Pin(26))  # Joystick 1 → Servo (0..60°)
adc_motor = ADC(Pin(27))  # Joystick 2 → Motor (0..100%)

def leer_servo():
    raw = adc_servo.read_u16()
    # Mapear 0..65535 → 0..60 grados
    ang = int((raw * 60) / 65535)
    return max(0, min(60, ang))

def leer_motor():
    raw = adc_motor.read_u16()
    vel = int((raw * 100) / 65535)
    return max(0, min(100, vel))

def checksum(sync, ang, vel):
    return (sync + (ang & 0xFF) + ((ang >> 8) & 0xFF)
                 + (vel & 0xFF) + ((vel >> 8) & 0xFF)) & 0xFF

SYNC_BYTE = 0xA5
ultimo_s, ultimo_m = -1, -1
fallos_consecutivos = 0
MAX_FALLOS_CONSECUTIVOS = 10  # Aumentamos el umbral

print("🎮 TX Dual Joystick listo (Servo GP26 | Motor GP27)")

while True:
    s = leer_servo()
    m = leer_motor()
    chk = checksum(SYNC_BYTE, s, m)
    paquete = struct.pack("<BHHB", SYNC_BYTE, s, m, chk)

    if nrf is None:
        # Intentar recuperar el NRF si quedó en None
        iniciar_nrf()

    if nrf is not None:
        try:
            nrf.send(paquete)
            # Si cambió algo, lo mostramos (igual que antes)
            if s != ultimo_s or m != ultimo_m:
                print(f"📤 Servo:{s:3d}° | Motor:{m:3d}%")
                ultimo_s, ultimo_m = s, m
            # Envío exitoso → reset contador de fallos
            fallos_consecutivos = 0

        except Exception as e:
            fallos_consecutivos += 1
            print(f"❌ Error TX ({fallos_consecutivos}): {e}")
            # Limpiar flags de estado del NRF
            try:
                nrf.reg_write(0x07, 0x70)
            except:
                pass

            # Si acumula varios fallos seguidos → reinicializar radio
            if fallos_consecutivos >= MAX_FALLOS_CONSECUTIVOS:
                print("⚠ Muchos errores seguidos → reiniciando NRF TX...")
                iniciar_nrf()
                fallos_consecutivos = 0

    utime.sleep_ms(10) 
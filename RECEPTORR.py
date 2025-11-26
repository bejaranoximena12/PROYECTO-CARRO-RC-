# pico_w_receptor_nrf.py
from machine import UART, Pin, SPI
import network
import time
import struct
from nrf24l01 import NRF24L01

# =================== CONFIGURACIÓN WiFi ===================
WIFI_SSID = "RACE_2025"
WIFI_PASS = "987654321"

IP_SERVIDOR = "10.10.10.10"
PUERTO = 5000
CAR_ID = "CAR_GUIDO"
TEAM_NAME = "A los pits"


API_LAP_URL = "http://{}:{}/api/lap".format(IP_SERVIDOR, PUERTO)

CAR_ID = "CAR_GUIDO"
TEAM_NAME = "A los pits"

# =================== CONFIGURACIÓN NRF24L01 ===================
CHANNEL = 76
ADDR = b"\xC3\xF0\xF0\xF0\xF0"
PAYLOAD_SIZE = 32

# Configuración SPI para NRF24L01 - SPI1, GP10-11-12, CE=13, CSN=14
spi = SPI(1, sck=Pin(10), mosi=Pin(11), miso=Pin(12))
csn = Pin(14, Pin.OUT, value=1)
ce = Pin(13, Pin.OUT, value=0)

SEND_PERIOD_S = 1   # cada segundo
# =================== CONEXIÓN WiFi ===================
def conectar_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    if not wlan.isconnected():
        print(f"📡 Conectando a WiFi: {WIFI_SSID}")
        wlan.connect(WIFI_SSID, WIFI_PASS)
        
        timeout = 15
        while not wlan.isconnected() and timeout > 0:
            print(".", end="")
            time.sleep(1)
            timeout -= 1
        
        if wlan.isconnected():
            print(f"\n✅ WiFi conectado!")
            print(f"   IP: {wlan.ifconfig()[0]}")
            print(f"   Red: {WIFI_SSID}")
            return True
        else:
            print(f"\n❌ Error: No se pudo conectar a {WIFI_SSID}")
            return False
    else:
        print(f"✅ WiFi ya conectado")
        print(f"   IP: {wlan.ifconfig()[0]}")
        return True
    
def send_lap(lap_time_ms, lap_number):
    payload = {
        "car_id": CAR_ID,
        "team": TEAM_NAME,
        "lap_time_ms": lap_time_ms,
        "lap_number_debug": lap_number
    }
    try:
        print("Enviando lap:", payload)
        r = urequests.post(API_LAP_URL, json=payload)
        print("Respuesta servidor:", r.status_code, r.text)
        r.close()
        LED.value(1)
        time.sleep(0.05)
        LED.value(0)
    except Exception as e:
        print("Error enviando lap:", e)

def gen_progressive_lap_time(last_lap_ms):
    # Primera vuelta entre 25 y 35 s
    if last_lap_ms is None:
        base = 25000
        extra = urandom.getrandbits(10) % 10000  # 0–9999 ms
        return base + extra
    # Vueltas siguientes: añadir 0–5 s
    extra = urandom.getrandbits(12) % 5001       # 0–5000 ms
    return last_lap_ms + extra


def envio():
    connect_wifi()
    print("Simulador listo: enviando vuelta cada", SEND_PERIOD_S, "s")

    lap_counter = 0
    last_lap_ms = None

    while True:
        lap_counter += 1
        lap_time_ms = gen_progressive_lap_time(last_lap_ms)
        last_lap_ms = lap_time_ms

        print("Vuelta simulada {}: {} ms".format(lap_counter, lap_time_ms))
        send_lap(lap_time_ms, lap_counter)

        time.sleep(SEND_PERIOD_S)



# =================== INICIALIZACIÓN NRF24L01 ===================
def inicializar_nrf():
    try:
        # Constructor: NRF24L01(spi, csn, ce, channel, payload_size)
        nrf = NRF24L01(spi, csn, ce, CHANNEL, PAYLOAD_SIZE)
        
        # Potencia máxima / velocidad baja (si el driver lo soporta)
        try:
            from nrf24l01 import POWER_3, SPEED_250K
            nrf.set_power_speed(POWER_3, SPEED_250K)
            print("Potencia=MAX, Velocidad=250 kbps")
        except:
            print("Driver sin set_power_speed, seguimos por defecto")

        # Escuchar en PIPE 0 con la misma dirección que usa el transmisor
        nrf.open_rx_pipe(0, ADDR)
        nrf.start_listening()

        print("📡 NRF24L01 listo en modo RX (canal", CHANNEL, ", payload", PAYLOAD_SIZE, "bytes)")
        return nrf
        
    except Exception as e:
        print(f"❌ Error inicializando NRF24L01: {e}")
        return None

# =================== CONFIGURACIÓN HARDWARE ===================
# Configurar UART0 hacia PC (TX=GP0)
uart_pc = UART(0, baudrate=1200, tx=Pin(0), rx=Pin(1))
led = Pin("LED", Pin.OUT)

# =================== PROGRAMA PRINCIPAL ===================
print("🔴 Pico W - Receptor NRF24L01 + WiFi")
print("Iniciando conexión WiFi...")

# Conectar a WiFi
wifi_ok = conectar_wifi()

# Inicializar NRF24L01
nrf = inicializar_nrf()

if not nrf:
    print("❌ No se puede continuar sin NRF24L01")
else:
    print("✅ Esperando datos NRF24L01...")

counter = 0
last_send_time = time.ticks_ms()
SEND_INTERVAL_MS = 500  # Enviar cada 500ms (2Hz)

while True:
    try:
        # ========== RECEPCIÓN NRF24L01 ==========
        if nrf.any():
            try:
                data = nrf.recv()
            except OSError as e:
                # error leyendo FIFO
                print("⚠ Error al recibir NRF:", e)
                data = None

            if data and len(data) == PAYLOAD_SIZE:
                # Desempaquetar: <ii12h
                try:
                    (
                        lat_i, lon_i,
                        alt_i, spd_i,
                        ax_i, ay_i, az_i,
                        gx_i, gy_i, line_state_i,
                        vbat_i, temp_i,
                        pwm_servo_i, pwm_motor_i
                    ) = struct.unpack("<ii12h", data)
                except Exception as e:
                    print("⚠ Error al decodificar struct:", e)
                    print("   RAW:", data)
                    time.sleep_ms(10)
                    continue

                # Convertir a unidades físicas
                lat = lat_i / 100000.0      # grados
                lon = lon_i / 100000.0
                alt = alt_i                 # metros
                spd = spd_i / 10.0          # km/h

                ax = ax_i / 100.0           # m/s2
                ay = ay_i / 100.0
                az = az_i / 100.0

                gx = gx_i / 100.0           # deg/s
                gy = gy_i / 100.0
                # line_state_i: 0 / 1

                vbat = vbat_i / 100.0       # V
                temp = temp_i / 10.0        # °C

                # Texto legible para consola (formato igual a tu imagen)
                linea_txt = (
                    f"ServoPWM:{pwm_servo_i:4d}us | "
                    f"MotorPWM:{pwm_motor_i:4d}us | "
                    f"Batt:{vbat:4.2f}V | "
                    f"ACC:X:{ax:+5.2f} Y:{ay:+5.2f} Z:{az:+5.2f} m/s2 | "
                    f"GYRO:X:{gx:+5.2f} Y:{gy:+5.2f} Z:---   deg/s | "
                    f"Linea:{line_state_i:d} | "
                    f"GPS:({lat:+8.5f},{lon:+8.5f}) Alt:{alt:4d}m Spd:{spd:5.1f}km/h | "
                    f"Temp:{temp:4.1f}C"
                )

                print(f"📡 #{counter:03d} DATOS NRF RECIBIDOS:")
                print(linea_txt)
                print("-" * 70)

                # ========== ENVÍO A PAGINA WEB (CON FRECUENCIA REDUCIDA) ==========
                current_time = time.ticks_ms()
                if time.ticks_diff(current_time, last_send_time) >= SEND_INTERVAL_MS:
                    # ENVIAR FORMATO CORRECTO PARA LA PÁGINA WEB
                    trama_web = (
                        f"ServoPWM:{pwm_servo_i}us | "
                        f"MotorPWM:{pwm_motor_i}us | "
                        f"Batt:{vbat:.2f}V | "
                        f"ACC:X:{ax:+.2f} Y:{ay:+.2f} Z:{az:+.2f} m/s2 | "
                        f"GYRO:X:{gx:+.2f} Y:{gy:+.2f} Z:--- deg/s | "
                        f"Linea:{line_state_i} | "
                        f"GPS:({lat:+.5f},{lon:+.5f}) Alt:{alt:.0f}m Spd:{spd:.1f}km/h | "
                        f"Temp:{temp:.1f}C"
                    )
                    
                    # Enviar por UART en el formato que el servidor web espera
                    try:
                        uart_pc.write(trama_web + '\n')
                        print(f"📤 ENVIADO A WEB: {trama_web}")
                        last_send_time = current_time
                    except:
                        print("❌ Error enviando por UART")

                # LED indicador
                led.value(1)
                time.sleep(0.05)
                led.value(0)

                counter += 1
                        
        time.sleep(0.02)  # Pequeña pausa

    except KeyboardInterrupt:
        print("\n🛑 Recepción detenida")
        break
    except Exception as e:
        print(f"❌ Error: {e}")
        time.sleep(1)
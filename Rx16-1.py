# ================= RX: MÁXIMA EFICIENCIA CONTROL + UART(no verificad) =================
from machine import Pin, SPI, PWM, ADC, UART
import utime, struct
from nrf24l01 import NRF24L01

# ---- LED indicador (GP20) ----
led = Pin(20, Pin.OUT)
led.off()
ultima_recepcion = utime.ticks_ms()
TIEMPO_SIN_SEÑAL = 2000

# ---- Servo dirección (GP15) ----
servo = PWM(Pin(15))
servo.freq(50)

def mover_servo_instantaneo(angulo):
    angulo = max(0, min(80, int(angulo)))
    pulso_us = 500 + (angulo * 2000) // 180
    servo.duty_ns(int(pulso_us * 1000))
    return pulso_us

# ---- Motor ESC (GP9) ----
esc = PWM(Pin(9))
esc.freq(50)

def controlar_motor(velocidad):
    velocidad = max(0, min(100, int(velocidad)))
    centered = velocidad - 50
    if abs(centered) < 5:
        centered = 0
    pulso_us = 1500 + centered * 10
    esc.duty_ns(int(pulso_us * 1000))
    return pulso_us

# ---- FAILSAFE ----
def failsafe():
    pwm_m = controlar_motor(50)
    pwm_s = mover_servo_instantaneo(40)
    print(f"🛑 FAILSAFE -> Servo CENTRO ({pwm_s} us) | Motor NEUTRO ({pwm_m} us)")

# ---- Radio NRF ----
spi = SPI(0, sck=Pin(6), mosi=Pin(7), miso=Pin(4))
csn = Pin(5, Pin.OUT, value=1)
ce  = Pin(14, Pin.OUT, value=0)

TX_ADDR = b'\xE1\xF0\xF0\xF0\xF0'
RX_ADDR = b'\xD2\xF0\xF0\xF0\xF0'

def iniciar_nrf():
    global nrf
    try:
        nrf = NRF24L01(spi, csn, ce, payload_size=8)
        nrf.open_tx_pipe(TX_ADDR)
        nrf.open_rx_pipe(1, RX_ADDR)
        nrf.set_power_speed(3, 2)
        nrf.reg_write(0x01, 0x00)
        nrf.reg_write(0x04, 0x00)
        nrf.reg_write(0x05, 100)
        nrf.reg_write(0x07, 0x70)
        nrf.start_listening()
        print("🔄 NRF reinicializado y escuchando...")
    except Exception as e:
        print("⚠ Error reiniciando NRF:", e)

iniciar_nrf()
print("📡 RX listo")

failsafe()
utime.sleep_ms(2000)

SYNC_BYTE = 0xA5

def verificar_checksum(sync, ang, vel, chk):
    calc = (sync + (ang & 0xFF) + ((ang >> 8) & 0xFF)
                 + (vel & 0xFF) + ((vel >> 8) & 0xFF)) & 0xFF
    return chk == calc

# -------------------------------------------------------------------
# --- BATERÍA (divisor 20k/10k = factor 3.0)
# -------------------------------------------------------------------
adc_bat = ADC(26)
FACTOR_DIVISOR = 3.0

def leer_bateria():
    raw = adc_bat.read_u16()
    v_adc = raw * 3.3 / 65535
    v_bat = v_adc * FACTOR_DIVISOR
    return v_bat

vbat_cache = leer_bateria()          # <-- valor inicial REAL
ultimo_print_bat = utime.ticks_ms()
# -------------------------------------------------------------------

# ---- UART0: telemetría hacia Placa 3 (GP0 = TX) ----
uart = UART(0, baudrate=115200, tx=Pin(0))
ultimo_envio_uart = 0
INTERVALO_UART = 20  # ms entre envíos UART (más rápido pero no bloqueante)

# ---- Variables cache para UART eficiente ----
angulo_actual = 40
velocidad_actual = 50
pwm_servo_actual = 1500
pwm_motor_actual = 1500

# ---- Bucle principal OPTIMIZADO ----
while True:
    ahora = utime.ticks_ms()
    
    # ⚡ PRIORIDAD 1: RECEPCIÓN Y CONTROL INMEDIATO
    if nrf.any():
        try:
            datos = nrf.recv()
            nrf.reg_write(0x07, 0x70)

            if len(datos) == 8:
                sync, angulo, velocidad, chk = struct.unpack("<BHHB", datos)

                if sync == SYNC_BYTE and verificar_checksum(sync, angulo, velocidad, chk):
                    # ⚡ CONTROL INMEDIATO (primero lo más importante)
                    pwm_servo_actual = mover_servo_instantaneo(angulo)
                    pwm_motor_actual = controlar_motor(velocidad)
                    
                    # Guardar estado para UART y display
                    angulo_actual = angulo
                    velocidad_actual = velocidad

                    ultima_recepcion = ahora
                    led.on()

                    # 🖨️ MOSTRAR EN CONSOLA (igual que antes)
                    print(f"📥 Servo:{angulo_actual:3d}° ({pwm_servo_actual} us) | "
                          f"Motor:{velocidad_actual:3d}% ({pwm_motor_actual} us) | "
                          f"Batt:{vbat_cache:.2f} V")

        except Exception as e:
            print("❌ Error RX:", e)

    # ⚡ PRIORIDAD 2: UART NO BLOQUEANTE (después del control)
    if utime.ticks_diff(ahora, ultimo_envio_uart) > INTERVALO_UART:
        try:
            # 📡 ENVIAR TELEMETRÍA A PLACA 3 (mismo formato)
            linea = f"{angulo_actual},{velocidad_actual},{pwm_servo_actual},{pwm_motor_actual},{vbat_cache:.2f}\n"
            uart.write(linea)
            ultimo_envio_uart = ahora
        except Exception as e:
            print("⚠ Error UART TX:", e)

    # ⚡ PRIORIDAD 3: ACTUALIZAR BATERÍA CADA 1s
    if utime.ticks_diff(ahora, ultimo_print_bat) > 1000:
        vbat_cache = leer_bateria()
        print(f"🔋 Batt:{vbat_cache:.2f} V")
        ultimo_print_bat = ahora

    # ⚡ PRIORIDAD 4: VERIFICAR FAILSAFE
    if utime.ticks_diff(ahora, ultima_recepcion) > TIEMPO_SIN_SEÑAL:
        failsafe()
        led.toggle()
        print("❌ Señal perdida → FAILSAFE → reiniciando NRF")
        iniciar_nrf()
        utime.sleep_ms(300)
        # Resetear variables después del failsafe
        angulo_actual = 40
        velocidad_actual = 50
        continue

    utime.sleep_us(250)  # ⚡ Loop ligeramente más rápido
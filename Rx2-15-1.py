# ==================== Placa 3 – Receptor UART de telemetría ====================
from machine import UART, Pin
import utime

# UART0: RX en GP1 (desde GP0 TX de Placa 2)
uart = UART(0, baudrate=115200, rx=Pin(1))

print("📡 Placa 3 lista para recibir telemetría...")

while True:
    if uart.any():
        try:
            linea = uart.readline()
            if not linea:
                continue

            # Convertir a texto
            try:
                texto = linea.decode().strip()
            except:
                continue

            # Esperado: angulo,velocidad,pwm_servo,pwm_motor,voltaje
            datos = texto.split(",")

            if len(datos) == 5:
                angulo    = int(datos[0])
                velocidad = int(datos[1])
                pwm_servo = int(datos[2])
                pwm_motor = int(datos[3])
                vbat      = float(datos[4])

                # === Solo 3 columnas claras ===
                print(f"Servo:{angulo:3d}° ({pwm_servo} us) | "
                      f"Motor:{velocidad:3d}% ({pwm_motor} us) | "
                      f"Batt:{vbat:0.2f} V")

        except Exception as e:
            # Evita fallos si llega alguna línea incompleta
            print("⚠ Error UART:", e)

    utime.sleep_ms(5)


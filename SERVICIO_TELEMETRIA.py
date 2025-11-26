"""
Script Python para PC - Telemetría Raspberry Pico 2
Servidor Web Mejorado - BAUD RATE 1200 con Sensor de Línea
"""
import serial
import json
import webbrowser
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import time
import re
from datetime import datetime

# ============ CONFIGURACIÓN ============
PUERTO_COM = 'COM6'
BAUDRATE = 1200  # Cambiado a 1200 baudios
PUERTO_WEB = 8080

# ============ DATOS GLOBALES ============
telemetry_data = {
    "gps": {"latitude": 0.0, "longitude": 0.0, "altitude": 0.0, "speed": 0.0},
    "accelerometer": {"x": 0.0, "y": 0.0, "z": 0.0},
    "gyroscope": {"x": 0.0, "y": 0.0, "z": 0.0},
    "servo": {"angle": 0.0},
    "motor": {"speed": 0.0},
    "battery": {"voltage": 0.0},
    "temperature": {"value": 0.0},
    "line_sensor": {"value": 0, "status": "DESCONOCIDO"},  # Nuevo sensor de línea
    "counter": {"value": 0},
    "data_rate": {"hz": 0.0}
}

connection_status = {"connected": False}
last_update_time = datetime.now()

# ============ LECTURA DE PUERTO SERIE ============
def leer_puerto_serie():
    global telemetry_data, connection_status, last_update_time
    
    print(f"Conectando a {PUERTO_COM} a {BAUDRATE} baudios...")
    
    while True:
        try:
            with serial.Serial(PUERTO_COM, BAUDRATE, timeout=2) as ser:  # Timeout aumentado
                print(f"✓ Puerto {PUERTO_COM} abierto a {BAUDRATE} baudios")
                connection_status["connected"] = True
                ser.reset_input_buffer()
                
                while True:
                    if ser.in_waiting > 0:
                        try:
                            linea = ser.readline().decode('utf-8', errors='ignore').strip()
                            if linea:
                                print(f"📨 Recibido: {linea}")
                                if parsear_telemetria(linea):
                                    connection_status["connected"] = True
                                    last_update_time = datetime.now()
                        except Exception as e:
                            print(f"Error lectura: {e}")
                    
                    time.sleep(0.05)  # Aumentado para 1200 baudios
                    
        except Exception as e:
            print(f"✗ Error puerto: {e}")
            connection_status["connected"] = False
            time.sleep(3)  # Mayor tiempo de espera

def parsear_telemetria(linea):
    global telemetry_data
    
    try:
        # Servo PWM
        servo_match = re.search(r'ServoPWM:(\d+)us', linea)
        if servo_match:
            servo_us = int(servo_match.group(1))
            servo_angle = ((servo_us - 1000) / 1000) * 180
            telemetry_data["servo"]["angle"] = max(0, min(180, servo_angle))
        
        # Motor PWM
        motor_match = re.search(r'MotorPWM:(\d+)us', linea)
        if motor_match:
            motor_us = int(motor_match.group(1))
            motor_speed = ((motor_us - 1500) / 500) * 100
            telemetry_data["motor"]["speed"] = max(-100, min(100, motor_speed))
        
        # Batería
        batt_match = re.search(r'Batt:([\d.]+)V', linea)
        if batt_match:
            telemetry_data["battery"]["voltage"] = float(batt_match.group(1))
        
        # Acelerómetro
        acc_match = re.search(r'ACC:X:([+-]?[\d.]+)\s+Y:([+-]?[\d.]+)\s+Z:([+-]?[\d.]+)\s+m/s2', linea)
        if acc_match:
            telemetry_data["accelerometer"]["x"] = float(acc_match.group(1))
            telemetry_data["accelerometer"]["y"] = float(acc_match.group(2))
            telemetry_data["accelerometer"]["z"] = float(acc_match.group(3))
        
        # Giroscopio
        gyro_match = re.search(r'GYRO:X:([+-]?[\d.-]+)\s+Y:([+-]?[\d.-]+)\s+Z:([+-]?[\d.-]+)', linea)
        if gyro_match:
            gx = gyro_match.group(1)
            gy = gyro_match.group(2)
            gz = gyro_match.group(3)
            if gx != '---':
                telemetry_data["gyroscope"]["x"] = float(gx)
            if gy != '---':
                telemetry_data["gyroscope"]["y"] = float(gy)
            if gz != '---':
                telemetry_data["gyroscope"]["z"] = float(gz)
        
        # GPS
        gps_match = re.search(r'GPS:\(([+-]?[\d.]+),([+-]?[\d.]+)\)\s+Alt:([\d.]+)m\s+Spd:([\d.]+)km/h', linea)
        if gps_match:
            telemetry_data["gps"]["latitude"] = float(gps_match.group(1))
            telemetry_data["gps"]["longitude"] = float(gps_match.group(2))
            telemetry_data["gps"]["altitude"] = float(gps_match.group(3))
            telemetry_data["gps"]["speed"] = float(gps_match.group(4))
        
        # Temperatura
        temp_match = re.search(r'Temp:([\d.]+)C', linea)
        if temp_match:
            telemetry_data["temperature"]["value"] = float(temp_match.group(1))
        
        # Sensor de Línea - Nuevo
        line_match = re.search(r'Line:(\d)', linea)
        if line_match:
            line_value = int(line_match.group(1))
            telemetry_data["line_sensor"]["value"] = line_value
            # 0 = Sobre la línea, 1 = Fuera de la línea
            if line_value == 0:
                telemetry_data["line_sensor"]["status"] = "SOBRE LÍNEA"
            else:
                telemetry_data["line_sensor"]["status"] = "FUERA LÍNEA"
        
        return True
        
    except Exception as e:
        print(f"✗ Error parseando: {e}")
        return False

# ============ SERVIDOR WEB ============
class TelemetryHandler(BaseHTTPRequestHandler):
    
    def do_GET(self):
        if self.path == '/':
            self.serve_html()
        elif self.path == '/telemetry':
            self.serve_telemetry()
        elif self.path == '/state':
            self.serve_state()
        else:
            self.send_error(404)
    
    def serve_html(self):
        try:
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            
            html = self.get_html_page()
            self.wfile.write(html.encode('utf-8'))
        except Exception as e:
            print(f"✗ Error sirviendo HTML: {e}")
    
    def serve_telemetry(self):
        try:
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            json_data = json.dumps(telemetry_data)
            self.wfile.write(json_data.encode('utf-8'))
        except Exception as e:
            print(f"✗ Error sirviendo JSON: {e}")
    
    def serve_state(self):
        try:
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            estado = {
                "connected": connection_status["connected"],
                "last_update": last_update_time.isoformat(),
                "telemetry": telemetry_data
            }
            json_data = json.dumps(estado)
            self.wfile.write(json_data.encode('utf-8'))
        except Exception as e:
            print(f"✗ Error sirviendo estado: {e}")
    
    def log_message(self, format, *args):
        pass
    
    def get_html_page(self):
        return '''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>📡 Telemetría Raspberry Pico 2 - 1200 Baud</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            color: #f1f5f9;
            padding: 20px;
            min-height: 100vh;
        }
        
        .container { max-width: 1400px; margin: 0 auto; }
        
        header { text-align: center; margin-bottom: 30px; }
        
        h1 {
            font-size: 2.5em;
            background: linear-gradient(135deg, #10b981, #3b82f6);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 10px;
        }
        
        .subtitle { color: #94a3b8; font-size: 1.1em; }
        
        .baud-info {
            background: rgba(245, 158, 11, 0.2);
            padding: 10px 20px;
            border-radius: 10px;
            margin: 10px auto;
            display: inline-block;
            border: 1px solid rgba(245, 158, 11, 0.5);
            color: #f59e0b;
            font-weight: bold;
        }
        
        .speed-warning {
            background: rgba(239, 68, 68, 0.2);
            padding: 8px 16px;
            border-radius: 8px;
            margin: 5px auto;
            display: inline-block;
            border: 1px solid rgba(239, 68, 68, 0.5);
            color: #ef4444;
            font-size: 0.9em;
        }
        
        .status-card {
            background: linear-gradient(145deg, #1e293b, #334155);
            border-radius: 16px;
            padding: 20px;
            margin-bottom: 25px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
            border: 1px solid rgba(255, 255, 255, 0.1);
            display: flex;
            align-items: center;
            gap: 20px;
            transition: all 0.3s ease;
        }
        
        .status-card.connected {
            background: linear-gradient(145deg, #065f46, #047857);
            border-color: #10b981;
        }
        
        .status-card.disconnected {
            background: linear-gradient(145deg, #7f1d1d, #991b1b);
            border-color: #ef4444;
        }
        
        .line-status-card {
            background: linear-gradient(145deg, #1e293b, #334155);
            border-radius: 16px;
            padding: 20px;
            margin-bottom: 25px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
            border: 1px solid rgba(255, 255, 255, 0.1);
            display: flex;
            align-items: center;
            gap: 20px;
            transition: all 0.3s ease;
        }
        
        .line-status-card.on-line {
            background: linear-gradient(145deg, #065f46, #047857);
            border-color: #10b981;
        }
        
        .line-status-card.off-line {
            background: linear-gradient(145deg, #dc2626, #b91c1c);
            border-color: #ef4444;
        }
        
        .line-status-card.unknown {
            background: linear-gradient(145deg, #475569, #374151);
            border-color: #94a3b8;
        }
        
        .status-icon { font-size: 2.5em; }
        
        .status-text h2 { font-size: 1.5em; margin-bottom: 5px; }
        
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 25px;
            margin-bottom: 25px;
        }
        
        .card {
            background: linear-gradient(145deg, #1e293b, #2d3748);
            border-radius: 16px;
            padding: 25px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        
        .card-header {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 2px solid rgba(16, 185, 129, 0.3);
        }
        
        .card-icon {
            background: rgba(16, 185, 129, 0.2);
            padding: 10px;
            border-radius: 12px;
            font-size: 1.5em;
        }
        
        .card-title { font-size: 1.3em; font-weight: 600; }
        
        .data-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }
        
        .data-row:last-child { border-bottom: none; }
        
        .data-label { color: #94a3b8; font-weight: 500; }
        
        .data-value {
            font-family: 'Courier New', monospace;
            font-size: 1.1em;
            font-weight: bold;
            color: #10b981;
        }
        
        .unit { color: #64748b; font-size: 0.9em; margin-left: 5px; }
        
        .map-button {
            width: 100%;
            background: linear-gradient(135deg, #10b981, #059669);
            color: white;
            border: none;
            padding: 15px;
            border-radius: 12px;
            font-size: 1.1em;
            font-weight: 600;
            cursor: pointer;
            margin-top: 15px;
        }
        
        .map-button:disabled {
            background: #475569;
            cursor: not-allowed;
        }
        
        .temp-bar {
            width: 100%;
            height: 8px;
            background: #334155;
            border-radius: 10px;
            overflow: hidden;
            margin-top: 10px;
        }
        
        .temp-fill {
            height: 100%;
            background: linear-gradient(90deg, #3b82f6, #f59e0b);
            transition: width 0.5s ease;
            border-radius: 10px;
        }
        
        footer {
            text-align: center;
            color: #64748b;
            margin-top: 30px;
            padding: 20px;
            background: rgba(30, 41, 59, 0.5);
            border-radius: 12px;
        }
        
        .last-update { color: #94a3b8; font-size: 0.9em; margin-top: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📡 Telemetría Raspberry Pico 2</h1>
            <p class="subtitle">Monitor en Tiempo Real - Puerto COM6</p>
            <div class="baud-info">
                <strong>Velocidad: 1200 baudios</strong>
            </div>
            <div class="speed-warning">
                ⚠️ Velocidad baja - Actualización más lenta
            </div>
            <p class="last-update" id="lastUpdate">Esperando datos...</p>
        </header>
        
        <div class="status-card disconnected" id="statusCard">
            <div class="status-icon">📶</div>
            <div class="status-text">
                <h2 id="statusTitle">DESCONECTADO</h2>
                <p id="statusDesc">Esperando conexión con el dispositivo</p>
            </div>
        </div>
        
        <!-- Nuevo Card para Sensor de Línea -->
        <div class="line-status-card unknown" id="lineStatusCard">
            <div class="status-icon" id="lineIcon">❓</div>
            <div class="status-text">
                <h2 id="lineTitle">SENSOR DE LÍNEA</h2>
                <p id="lineDesc">Esperando datos del sensor...</p>
            </div>
        </div>
        
        <div class="grid">
            <!-- GPS Card -->
            <div class="card">
                <div class="card-header">
                    <div class="card-icon">📍</div>
                    <div class="card-title">Posición GPS</div>
                </div>
                <div class="data-row">
                    <span class="data-label">Latitud</span>
                    <span class="data-value"><span id="lat">0.000000</span><span class="unit">°</span></span>
                </div>
                <div class="data-row">
                    <span class="data-label">Longitud</span>
                    <span class="data-value"><span id="lon">0.000000</span><span class="unit">°</span></span>
                </div>
                <div class="data-row">
                    <span class="data-label">Altitud</span>
                    <span class="data-value"><span id="alt">0.0</span><span class="unit">m</span></span>
                </div>
                <div class="data-row">
                    <span class="data-label">Velocidad</span>
                    <span class="data-value"><span id="spd">0.0</span><span class="unit">km/h</span></span>
                </div>
                <button class="map-button" id="mapButton" onclick="openGoogleMaps()">
                    🗺️ Abrir en Google Maps
                </button>
            </div>
            
            <!-- Accelerometer Card -->
            <div class="card">
                <div class="card-header">
                    <div class="card-icon">⚡</div>
                    <div class="card-title">Acelerómetro</div>
                </div>
                <div class="data-row">
                    <span class="data-label">Eje X</span>
                    <span class="data-value"><span id="accx">0.000</span><span class="unit">m/s²</span></span>
                </div>
                <div class="data-row">
                    <span class="data-label">Eje Y</span>
                    <span class="data-value"><span id="accy">0.000</span><span class="unit">m/s²</span></span>
                </div>
                <div class="data-row">
                    <span class="data-label">Eje Z</span>
                    <span class="data-value"><span id="accz">0.000</span><span class="unit">m/s²</span></span>
                </div>
            </div>
            
            <!-- Gyroscope Card -->
            <div class="card">
                <div class="card-header">
                    <div class="card-icon">🧭</div>
                    <div class="card-title">Giroscopio</div>
                </div>
                <div class="data-row">
                    <span class="data-label">Eje X</span>
                    <span class="data-value"><span id="gyrox">0.000</span><span class="unit">°/s</span></span>
                </div>
                <div class="data-row">
                    <span class="data-label">Eje Y</span>
                    <span class="data-value"><span id="gyroy">0.000</span><span class="unit">°/s</span></span>
                </div>
                <div class="data-row">
                    <span class="data-label">Eje Z</span>
                    <span class="data-value"><span id="gyroz">0.000</span><span class="unit">°/s</span></span>
                </div>
            </div>
            
            <!-- Actuators Card -->
            <div class="card">
                <div class="card-header">
                    <div class="card-icon">⚙️</div>
                    <div class="card-title">Actuadores</div>
                </div>
                <div class="data-row">
                    <span class="data-label">Ángulo Servo</span>
                    <span class="data-value"><span id="servo">0</span><span class="unit">°</span></span>
                </div>
                <div class="data-row">
                    <span class="data-label">Velocidad Motor</span>
                    <span class="data-value"><span id="motor">0.0</span><span class="unit">%</span></span>
                </div>
                <div class="data-row">
                    <span class="data-label">Batería</span>
                    <span class="data-value"><span id="batt">0.00</span><span class="unit">V</span></span>
                </div>
            </div>
            
            <!-- Temperature Card -->
            <div class="card">
                <div class="card-header">
                    <div class="card-icon">🌡️</div>
                    <div class="card-title">Temperatura</div>
                </div>
                <div class="data-row">
                    <span class="data-label">Temperatura Actual</span>
                    <span class="data-value"><span id="temp">0.0</span><span class="unit">°C</span></span>
                </div>
                <div class="temp-bar">
                    <div class="temp-fill" id="tempBar" style="width: 0%"></div>
                </div>
            </div>
        </div>
        
        <footer>
            <p>Sistema de Telemetría · Raspberry Pico 2 · 1200 Baudios</p>
            <p>Recibiendo datos vía UART desde COM6</p>
        </footer>
    </div>

    <script>
        let gpsLat = 0, gpsLon = 0;
        let updateInProgress = false;
        
        function updateUI(data) {
            if (updateInProgress) return;
            updateInProgress = true;
            
            // GPS
            gpsLat = data.gps.latitude;
            gpsLon = data.gps.longitude;
            document.getElementById('lat').textContent = data.gps.latitude.toFixed(6);
            document.getElementById('lon').textContent = data.gps.longitude.toFixed(6);
            document.getElementById('alt').textContent = data.gps.altitude.toFixed(1);
            document.getElementById('spd').textContent = data.gps.speed.toFixed(1);
            
            // Acelerómetro
            document.getElementById('accx').textContent = data.accelerometer.x.toFixed(3);
            document.getElementById('accy').textContent = data.accelerometer.y.toFixed(3);
            document.getElementById('accz').textContent = data.accelerometer.z.toFixed(3);
            
            // Giroscopio
            document.getElementById('gyrox').textContent = data.gyroscope.x.toFixed(3);
            document.getElementById('gyroy').textContent = data.gyroscope.y.toFixed(3);
            document.getElementById('gyroz').textContent = data.gyroscope.z.toFixed(3);
            
            // Actuadores
            document.getElementById('servo').textContent = Math.round(data.servo.angle);
            document.getElementById('motor').textContent = data.motor.speed.toFixed(1);
            document.getElementById('batt').textContent = data.battery.voltage.toFixed(2);
            
            // Temperatura
            const temp = data.temperature.value;
            document.getElementById('temp').textContent = temp.toFixed(1);
            const tempPercent = Math.min(100, (temp / 50) * 100);
            document.getElementById('tempBar').style.width = tempPercent + '%';
            
            // Sensor de Línea - Nuevo
            updateLineSensor(data.line_sensor);
            
            // Actualizar timestamp
            const now = new Date();
            document.getElementById('lastUpdate').textContent = 
                'Última actualización: ' + now.toLocaleTimeString();
            
            updateInProgress = false;
        }

        function updateLineSensor(lineData) {
            const card = document.getElementById('lineStatusCard');
            const title = document.getElementById('lineTitle');
            const desc = document.getElementById('lineDesc');
            const icon = document.getElementById('lineIcon');
            
            const lineValue = lineData.value;
            const status = lineData.status;
            
            if (status === "SOBRE LÍNEA") {
                card.className = 'line-status-card on-line';
                title.textContent = 'SOBRE LA LÍNEA ✓';
                desc.textContent = 'El vehículo está siguiendo la línea correctamente';
                icon.textContent = '✅';
            } else if (status === "FUERA LÍNEA") {
                card.className = 'line-status-card off-line';
                title.textContent = 'FUERA DE LÍNEA ✗';
                desc.textContent = 'El vehículo se ha salido de la línea';
                icon.textContent = '❌';
            } else {
                card.className = 'line-status-card unknown';
                title.textContent = 'SENSOR DE LÍNEA';
                desc.textContent = 'Esperando datos del sensor...';
                icon.textContent = '❓';
            }
        }

        function updateStatus(connected) {
            const card = document.getElementById('statusCard');
            const title = document.getElementById('statusTitle');
            const desc = document.getElementById('statusDesc');
            const mapBtn = document.getElementById('mapButton');
            
            if (connected) {
                card.className = 'status-card connected';
                title.textContent = 'CONECTADO ✓';
                desc.textContent = 'Recibiendo datos de telemetría en tiempo real';
                mapBtn.disabled = false;
            } else {
                card.className = 'status-card disconnected';
                title.textContent = 'DESCONECTADO ✗';
                desc.textContent = 'No hay conexión con el dispositivo';
                mapBtn.disabled = true;
            }
        }
        
        function openGoogleMaps() {
            if (gpsLat === 0 && gpsLon === 0) {
                alert('⚠️ No hay coordenadas GPS disponibles');
                return;
            }
            const url = `https://www.google.com/maps?q=${gpsLat},${gpsLon}`;
            window.open(url, '_blank');
        }

        // Polling optimizado para 1200 baudios (más lento)
        function fetchData() {
            fetch('/telemetry')
                .then(response => {
                    if (!response.ok) throw new Error('HTTP error');
                    return response.json();
                })
                .then(data => {
                    updateStatus(true);
                    updateUI(data);
                })
                .catch(error => {
                    updateStatus(false);
                });
        }

        // Polling cada 2000ms (más lento para 1200 baudios)
        setInterval(fetchData, 2000);

        // Carga inicial
        fetchData();
    </script>
</body>
</html>'''

def iniciar_servidor_web():
    try:
        server = HTTPServer(('localhost', PUERTO_WEB), TelemetryHandler)
        print(f"🚀 Servidor web en: http://localhost:{PUERTO_WEB}")
        print(f"📊 Velocidad: {BAUDRATE} baudios")
        print("⏳ Esperando datos... (Velocidad baja - Paciencia)")
        
        webbrowser.open(f'http://localhost:{PUERTO_WEB}')
        server.serve_forever()
    except Exception as e:
        print(f"❌ Error servidor: {e}")

# ============ MAIN ============
if __name__ == "__main__":
    print("=" * 50)
    print("SERVIDOR WEB TELEMETRÍA - 1200 BAUDIOS")
    print("=" * 50)
    print("⚠️  ADVERTENCIA: Velocidad muy baja")
    print("⏰ Las actualizaciones serán más lentas")
    print("📏 Sensor de línea incluido: 0=Sobre línea, 1=Fuera línea")
    print("=" * 50)
    
    threading.Thread(target=leer_puerto_serie, daemon=True).start()
    iniciar_servidor_web()
import serial
import time

def send_command_and_read_response(ser, command, response_length=7):
    try:
        # Komutu gönder
        ser.write(command)
        time.sleep(0.1)  # Küçük bir gecikme ekleyin

        # Gelen veriyi oku
        response = ser.read(response_length)
        return response

    except serial.SerialException as e:
        print(f"Seri port hatası: {e}")
        return None

def parse_response(response):
    if len(response) >= 5:
        # Dördüncü ve beşinci byte'ları al
        value = response[3] << 8 | response[4]
        return value
    return None

def scale_value(value, min_val, max_val, min_dist, max_dist):
    """Gelen değeri belirli aralıklara göre ölçeklendir."""
    if value < min_val:
        return "Out of range"
    elif value > max_val:
        return "Out of range"
    else:
        # Lineer ölçeklendirme
        scaled_value = min_dist + (value - min_val) * (max_dist - min_dist) / (max_val - min_val)
        return scaled_value

def read_from_serial(port='COM6', baudrate=9600, timeout=1):
    command = bytes.fromhex('01 04 00 00 00 01 31 CA')
    min_val = 4000
    max_val = 20000
    min_dist = 297  # mm
    max_dist = 832  # mm

    try:
        ser = serial.Serial(port, baudrate, timeout=timeout)
        print(f"Bağlantı kuruldu: {ser.name}")

        while True:
            response = send_command_and_read_response(ser, command)
            if response:
                value = parse_response(response)
                if value is not None:
                    scaled_value = scale_value(value, min_val, max_val, min_dist, max_dist)
                    print(f"Gelen değer: {value}, Ölçeklendirilmiş değer: {scaled_value} mm")
                else:
                    print("Geçersiz yanıt")
            time.sleep(1)  # Her saniyede bir komut gönder ve yanıtı oku

    except serial.SerialException as e:
        print(f"Seri port hatası: {e}")
    except KeyboardInterrupt:
        print("Bağlantı sonlandırıldı.")
    finally:
        if ser.is_open:
            ser.close()
            print("Seri port kapatıldı.")

if __name__ == "__main__":
    read_from_serial()
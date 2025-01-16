def parse_gpchc_message(message):
    """
    Parses a $GPCHC message into a dictionary.
    Extracts the Status and Warning fields into separate dictionaries.
    
    Args:
        message (str): The GPCHC message as a string.
    
    Returns:
        dict: Parsed message data, including nested dictionaries for Status and Warning.
    """
    fields = [
        "Header", "GPSWeek", "GPSTime", "Heading", "Pitch", "Roll", "gyro x", "gyro y", "gyro z",
        "acc x", "acc y", "acc z", "Latitude", "Longitude", "Altitude", "Ve", "Vn", "Vu", "V",
        "NSV1", "NSV2", "Status", "Age", "Warning", "Cs"
    ]
    
    # Remove $ and <CR><LF> from the message, split by ',' or '*'
    message_cleaned = message.strip().decode('utf-8').replace('$', '').split('*')
    data = message_cleaned[0].split(',') + [message_cleaned[1]]
    
    parsed_data = {}
    status_dict = {}
    warning_dict = {}
    
    for i, field in enumerate(fields):
        if field == "Status":
            status_value = int(data[i])
            status_dict["System State"] = status_value & 0xF  # Lower 4 bits
            status_dict["Satellite State"] = (status_value >> 4) & 0xF  # Upper 4 bits
            parsed_data[field] = status_dict
        elif field == "Warning":
            warning_value = int(data[i])
            warning_dict["No GPS message"] = (warning_value & 0b0001) != 0
            warning_dict["No velocity message"] = (warning_value & 0b0010) != 0
            warning_dict["gyro wrong"] = (warning_value & 0b0100) != 0
            warning_dict["acc wrong"] = (warning_value & 0b1000) != 0
            parsed_data[field] = warning_dict
        else:
            parsed_data[field] = data[i]
    
    return parsed_data

# Example message
message = b'$GPCHC,2342,210026.25,0.00,0.41,-0.17,0.34,-0.01,0.04,0.0028,0.0074,1.0000,0.00000000,0.00000000,0.00,0.000,0.000,0.000,0.000,4,0,00,0,0002*65\r\n'

# Parse the message
parsed_message = parse_gpchc_message(message)

# Display parsed message
print(parsed_message)

def interpret_status(status_dict):
    """
    Interprets the Status field from the parsed GPCHC message.

    Args:
        status_dict (dict): The Status field parsed as a dictionary with keys:
                            - "System State" (lower half byte)
                            - "Satellite State" (higher half byte)

    Returns:
        dict: A dictionary containing human-readable descriptions for both system and satellite states.
    """
    # Define the mapping for system state (lower half byte)
    system_state_map = {
        0: "Initialization",
        1: "Satellite navigation mode",
        2: "Integrated navigation mode",
        3: "IMU navigation mode"
    }

    # Define the mapping for satellite state (high half byte)
    satellite_state_map = {
        0: "No positioning and no orientation",
        1: "Single positioning and orientation",
        2: "DGPS positioning and orientation",
        3: "Integrated navigation",
        4: "RTK fixed positioning and orientation",
        5: "RTK float positioning and orientation",
        6: "Single positioning and no orientation",
        7: "DGPS positioning and no orientation",
        8: "RTK fixed positioning and no orientation",
        9: "RTK float positioning and no orientation"
    }

    # Extract system state and satellite state
    system_state = status_dict.get("System State", None)
    satellite_state = status_dict.get("Satellite State", None)

    # Translate states to human-readable descriptions
    system_description = system_state_map.get(system_state, "Unknown system state")
    satellite_description = satellite_state_map.get(satellite_state, "Unknown satellite state")

    return {
        "System State Description": system_description,
        "Satellite State Description": satellite_description
    }

# Example usage
status_example = {
    "System State": 2,  # Integrated navigation mode
    "Satellite State": 4  # RTK fixed positioning and orientation
}

# Interpret the status
interpreted_status = interpret_status(status_example)

# Display the result
print(interpreted_status)

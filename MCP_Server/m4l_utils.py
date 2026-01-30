import gzip
import json
import os

def set_parameter_default_value(input_filepath, output_filepath, parameter_name, new_default_value):
    """
    Reads a Max for Live device file (.amxd), changes the default value of a specified parameter,
    and writes the result to a new file.

    Args:
        input_filepath (str): The path to the input .amxd file.
        output_filepath (str): The path to write the modified .amxd file to.
        parameter_name (str): The name of the parameter to modify (its "long name" or "varname").
        new_default_value (float): The new default value for the parameter.

    Returns:
        bool: True if the modification was successful, False otherwise.
    """
    if not os.path.exists(input_filepath):
        raise FileNotFoundError(f"Input file not found: {input_filepath}")

    try:
        # Read and decompress the gzipped file
        with gzip.open(input_filepath, 'rb') as f:
            json_data = f.read()

        # Parse the JSON data
        data = json.loads(json_data)

        # Find and modify the parameter
        modified = False
        if "patcher" in data and "boxes" in data["patcher"]:
            for item in data["patcher"]["boxes"]:
                box = item.get("box")
                if not box:
                    continue

                # Check for parameter name in varname or parameter_longname
                varname = box.get("varname")
                longname = None
                if "saved_attribute_attributes" in box and "valueof" in box["saved_attribute_attributes"]:
                    longname = box["saved_attribute_attributes"]["valueof"].get("parameter_longname")

                if varname == parameter_name or longname == parameter_name:
                    # Found the parameter. Now find its initial value to modify.
                    # Based on research, the key is likely 'initial'.
                    if "initial" in box and isinstance(box["initial"], list) and len(box["initial"]) > 0:
                        box["initial"][0] = new_default_value
                        modified = True
                        break # Stop after finding the first match

        if not modified:
            raise ValueError(f"Parameter '{parameter_name}' not found or could not be modified.")

        # Convert the modified data back to a JSON string
        modified_json_data = json.dumps(data, indent=2)

        # Compress and write the new file
        with gzip.open(output_filepath, 'wb') as f:
            f.write(modified_json_data.encode('utf-8'))

        return True

    except FileNotFoundError:
        raise
    except Exception as e:
        # Re-raise exceptions with a more informative message
        raise type(e)(f"Failed to modify M4L device: {e}")

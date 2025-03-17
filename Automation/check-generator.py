import json
import csv
import os
import re

anonymize_checks = 0

def read_checks_from_csv(file_path):
    """
    Reads check definitions from a CSV file and converts them into a list of dictionaries.

    Args:
        file_path (str): Path to the CSV file.

    Returns:
        list of dict: List of checks with fields required for the template.
    """
    checks = []
    setup_params = {}
    
    with open(file_path, mode='r') as csvfile:
        reader = csv.reader(csvfile)
        rows = list(reader)
        
        # Extract setup parameters from rows 2-4
        setup_params["api_ip"] = rows[1][1].strip() # This is the cell
        setup_params["api_port"] = int(rows[2][1].strip())
        setup_params["repo_ip"] = rows[3][1].strip()
        
        # Determine if we're using shorthand or long name
        anonymize_checks = 1 if rows[5] == "Y" else 0

        # Grab the headers of the rows that follow
        headers = rows[8]

        # Extract the checks from rows below.
        for row in rows[9:]:
            check = {headers[i]: value for i, value in enumerate(row)}
            
            print("Check")
            print(check)
            check['arg-list'] = check['arg-list'].split(",")  # Convert comma-separated args into a list
            checks.append(check)
        
        return setup_params, checks   

def sanitize_filename(name):
    """
    Sanitizes a string to be safe for use as a filename by removing or replacing problematic characters.

    Args:
        name (str): The input string to sanitize.

    Returns:
        str: A sanitized version of the input string.
    """
    return re.sub(r'[\\/:*?"<>|]', '_', name)


def create_publish_checks(checks, api_address, api_port, repo_ip):
    """
    Updates the body of the template to include the 'repo-ip' and 'checks' field for the API.

    Args:
        checks (list of dict): List of check definitions with all necessary fields.
        api_address (str): API address.
        api_port (int): API port.
        repo_ip (str): The repository IP address to be included in the body.

    Returns:
        dict: The updated template with all checks and the 'repo-ip' field.
    """
    
    print(checks)
    
    # Create the "checks" array as per the new requirements
    checks_array = [
        {
            "target-agent": "{{.TeamNum}}-" + check["target-agent"],
            "target-script": check["target-script"],
            "run-method": check["run-method"],
            "arg-list": check["arg-list"]
        }
        for check in checks
    ]

    # Define the body with "repo-ip" and "checks"
    body = {"repo-ip": repo_ip, "checks": checks_array}

    # Define the single request
    request = {"host": "{{.API_Address}}",
               "path": "/publish-checks",
               "port": api_port,
               "https":False,
               "method":"POST",
               "headers":{"Content-Type":"application/json"},
               "matchcode":True,
               "code":200,
               "body":json.dumps(body,separators=(",",":"))}

    
    
    # Build the final template
    # Add the overridden attributes here
    # from the main dynamicbeat.yml file.
    # https://docs.scorestack.io/dynamicbeat/overrides.html?highlight=override#team-overrides
    template = {
        "name": "Publish Checks",
        "type": "http",
        "score_weight": 0,  # Default placeholder value
        "definition": {
            "requests": [request]
        },
        "attributes": {
            "admin": {
                "API_Address" : "{{.teamAPIAddress}}",
                "API_Port": "{{.teamAPIPort}}",
                "TeamNum": "{{.TeamNum}}"
            }
        }  
    }

    # Generate outputs
    pretty_body = json.dumps(body, indent=4)  # Nicely formatted JSON
    single_line_body = json.dumps(body, separators=(",", ":"))  # Single-line compact JSON

    return template, pretty_body, single_line_body



def create_read_checks(checks, api_address, api_port, repo_ip, score_weight):
    """
    Updates the body of the template to include the 'repo-ip' and 'checks' field for the API.

    Args:
        checks (list of dict): List of check definitions with all necessary fields.
        api_address (str): API address.
        api_port (int): API port.
        repo_ip (str): The repository IP address to be included in the body.
        score_weight (int): The weight of the score for the check.

    Returns:
        list of dict: List of updated templates for each check.
    """
    templates = []

    for check in checks:
        name = f"{check['target-agent']}-{check['target-script']}-{','.join(check['arg-list']).replace(' ', '_')}"
        sanitized_name = sanitize_filename(name)
        body = {
            "reporting-agent": "{{.TeamNum}}-" + check["target-agent"],
            "check-ran": check["target-script"],
            "arg-list": check["arg-list"]
        }
        
        request = {
            "host": "{{.API_Address}}",
            "path": "/read-result",
            "port": api_port,
            "https": False,
            "method": "POST",
            "headers": {"Content-Type": "application/json"},
            "matchcode": True,
            "code": 200,
            "body": json.dumps(body, separators=(",", ":"))
        }

        template = {
            "name": check["display-name"],
            "type": "http",
            "score_weight": int(check["score-weight"]),
            "definition": {
                "requests": [request]
            },
            "attributes": {
                "admin": {
                    "API_Address" : "{{.teamAPIAddress}}",
                    "API_Port": "{{.teamAPIPort}}",
                    "TeamNum": "{{.TeamNum}}"
                }
            }   
        }

        templates.append(template)

    return templates


def replace_api_port(template):
    """Recursively replaces '{{.API_Port}}' with {{.API_Port}} in the dictionary."""
    if isinstance(template, dict):
        for key, value in template.items():
            if key == "port" and value == "{{.API_Port}}":
                template[key] = "{{.API_Port}}"  # Keep it without quotes
            elif isinstance(value, (dict, list)):
                replace_api_port(value)
    elif isinstance(template, list):
        for item in template:
            replace_api_port(item)



def export_templates_to_files(templates, output_dir):
    """
    Exports each template to its own file in the specified directory.

    Args:
        templates (list of dict): List of templates to export.
        output_dir (str): Directory where the templates will be saved.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    SSPlaceHolderPrefix = "{{.TeamNum}}-"

    for template in templates:

        # Replace the API_Port in the template
        # replace_api_port(template)

        # This normalizes the filename.
        # e.g. external-http-http___google.com 
        # vs. {{.TeamNum}}-external-http-http__google.com
        file_name = f"{template['name']}.json"
        file_path = os.path.join(output_dir, file_name)
        
        with open(file_path, "w") as json_file:
            json.dump(template, json_file, indent=4)



if __name__ == "__main__":
    # Path to the CSV file containing checks
    csv_file_path = "checks.csv"

    # Read checks from the CSV file
    setup_params, checks = read_checks_from_csv(csv_file_path)

    # Generate the updated template and two outputs
    updated_template, pretty_body, single_line_body = create_publish_checks(checks, 
                                                                            setup_params["api_ip"], 
                                                                            setup_params["api_port"], 
                                                                            setup_params["repo_ip"])

    output_dir = "output-checks"

    # Create the output-checks directory if it doesn't exist
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)


    # Export the updated template to a JSON file
    with open(output_dir + "/publish-checks.json", "w") as json_file:
        json.dump(updated_template, json_file, indent=4)

    print("Template exported to publish-checks.json")

    # Print the nicely formatted body
    print("Pretty Body:\n", pretty_body)

    # Print the single-line body
    print("\nSingle-Line Body:\n", single_line_body)

    updated_templates = create_read_checks(checks, setup_params["api_ip"], setup_params["api_port"], setup_params["repo_ip"], 10)

    export_templates_to_files(updated_templates, output_dir)

    print("Read check templates exported to " + output_dir +  " directory")



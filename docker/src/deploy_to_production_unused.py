#!/usr/bin/env python
"""
Deployment script for CaseStrainer
Copies the necessary files to the production server and restarts the application
"""
import os
import sys
import subprocess
import shutil
import argparse
import time

# Production server details
PRODUCTION_SERVER = "wolf.law.uw.edu"
PRODUCTION_PATH = "/var/www/casestrainer"  # Adjust this path as needed


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Deploy CaseStrainer to production")
    parser.add_argument(
        "--restart",
        action="store_true",
        help="Restart the application after deployment",
    )
    return parser.parse_args()


def deploy_files():
    """Deploy the necessary files to the production server."""
    print("Deploying files to production server...")

    # Files to deploy
    files_to_deploy = [
        "app_final.py",
        "templates/fixed_form_ajax.html",
        "static/js/multitool_confirmed.js",
    ]

    # Create a temporary directory for deployment files
    temp_dir = "deployment_temp"
    os.makedirs(temp_dir, exist_ok=True)

    # Copy files to temporary directory
    for file_path in files_to_deploy:
        source_path = os.path.join(os.getcwd(), file_path)
        target_dir = os.path.join(temp_dir, os.path.dirname(file_path))
        os.makedirs(target_dir, exist_ok=True)

        if os.path.exists(source_path):
            shutil.copy2(source_path, os.path.join(temp_dir, file_path))
            print(f"Copied {file_path} to deployment package")
        else:
            print(f"Warning: {file_path} not found")

    # Create a deployment package
    deployment_zip = "casestrainer_deployment.zip"
    shutil.make_archive("casestrainer_deployment", "zip", temp_dir)
    print(f"Created deployment package: {deployment_zip}")

    # Copy the deployment package to the production server
    try:
        # Use SCP to copy the file to the production server
        scp_command = f"scp {deployment_zip} {PRODUCTION_SERVER}:{PRODUCTION_PATH}"
        print(f"Running: {scp_command}")
        subprocess.run(scp_command, shell=True, check=True)

        # Extract the deployment package on the production server
        ssh_extract_command = f"ssh {PRODUCTION_SERVER} 'cd {PRODUCTION_PATH} && unzip -o {deployment_zip}'"
        print(f"Running: {ssh_extract_command}")
        subprocess.run(ssh_extract_command, shell=True, check=True)

        print("Deployment completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error deploying files: {e}")
        return False
    finally:
        # Clean up temporary files
        if os.path.exists(deployment_zip):
            os.remove(deployment_zip)
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)


def restart_application():
    """Restart the CaseStrainer application on the production server."""
    print("Restarting CaseStrainer application...")

    try:
        # SSH into the production server and restart the application
        restart_command = f"ssh {PRODUCTION_SERVER} 'cd {PRODUCTION_PATH} && python run_production.py --host 0.0.0.0 --port 5000 &'"
        print(f"Running: {restart_command}")
        subprocess.run(restart_command, shell=True, check=True)

        print("Application restarted successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error restarting application: {e}")
        return False


def main():
    """Main function to deploy CaseStrainer to production."""
    args = parse_arguments()

    # Deploy files
    deployment_success = deploy_files()

    # Restart application if requested and deployment was successful
    if args.restart and deployment_success:
        restart_application()

    print("Deployment process completed")


if __name__ == "__main__":
    main()

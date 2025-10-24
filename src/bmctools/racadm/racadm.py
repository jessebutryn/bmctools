from misc.utils import is_command
import subprocess
import time
import shlex


class Racadm:
    """
    A class for interacting with Dell racadm command-line utility. This class provides methods for executing racadm commands and retrieving information from the server.

    Functions:
    - get(endpoint=None, arguments=[]): Executes a 'get' command with the specified endpoint and arguments.
    - set(endpoint=None, arguments=[]): Executes a 'set' command with the specified endpoint and arguments.
    - jobqueue_view(job): Retrieves detailed information about a specific job in the job queue.
    - jobqueue_status(job): Retrieves the status of a specific job in the job queue.
    - jobqueue_wait(job): Waits for a specific job in the job queue to complete.

    Sample Usage:
    racadm = Racadm(server)
    racadm.get('bios.sysprofilesettings')
    racadm.set('bios.sysprofilesettings', ['--enable', '1'])
    racadm.jobqueue_wait('JID_12345')
    """

    def __init__(self, ip, username, password):
        racadm = "/usr/local/bin/racadm"
        self.ip = ip
        self.username = username
        self.password = password

        if not is_command(racadm):
            raise FileNotFoundError("Dell racadm not found.  Ensure this is run from the toolbox")

        self.command = [
            racadm,
            "-r",
            self.ip,
            "-u",
            self.username,
            "-p",
            self.password,
            "--nocertwarn",
        ]

    def _dell_to_dict(self, input: str) -> dict:
        input = input.strip()
        input = input.splitlines()
        input = [
            line
            for line in input
            if line and not line.startswith("Security Alert:") and not line.startswith("Continuing execution.")
        ]

        # Find the index of the first non-empty line
        start_index = next((i for i, line in enumerate(input) if line.strip()), None)

        # Find the index of the last non-empty line
        end_index = next((i for i, line in reversed(list(enumerate(input))) if line.strip()), None)

        # Remove empty lines and strip leading/trailing whitespace from remaining lines
        input = [line.strip() for line in input[start_index : end_index + 1] if line.strip()]

        if "=" in input[0] and input[0].startswith("["):
            input[0] = input[0][1:-1]

            result = {}

            for line in input:
                if "=" in line:
                    key, value = line.split("=", 1)
                    result[key] = value

            return result
        else:
            return input

    def get(self, endpoint: str = None, arguments: list = [], format: bool = False) -> dict | str:
        _cmd = self.command + ["get"]
        if endpoint:
            _cmd += [endpoint]

        if arguments is not None:
            _cmd += list(arguments)

        result = subprocess.run(_cmd, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if result.returncode == 0:
            if format == True:
                out = self._dell_to_dict(result.stdout)
            else:
                out = result.stdout

            return out
        else:
            raise RuntimeError(result.stderr)

    def storage_get(self, endpoint: str = None, arguments: list = []) -> subprocess.CompletedProcess:
        _cmd = self.command + ["storage"] + ["get"]
        if endpoint:
            _cmd += [endpoint]

        if arguments is not None:
            _cmd += list(arguments)

        return subprocess.run(_cmd, capture_output=True, text=True)

    def check_vdisk(self, format: bool = False) -> dict | str | None:
        result = self.storage_get(arguments=["vdisks"])
        if result.returncode == 0:
            if format == True:
                out = self._dell_to_dict(result.stdout.strip())
            else:
                out = result.stdout.strip()
            return out
        elif result.returncode == 17 and "No virtual disks are displayed." in result.stdout:
            return None
        else:
            raise RuntimeError(result.stderr)

    def set(self, endpoint: str = None, arguments: list = []) -> str:
        _cmd = self.command + ["set"]
        if endpoint:
            _cmd += [endpoint]

        if arguments is not None:
            _cmd += list(arguments)

        result = subprocess.run(_cmd, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if result.returncode == 0:
            return result.stdout
        else:
            raise RuntimeError(result.stderr)

    def jobqueue_view(self, job: str) -> dict:
        job_dict = {}
        _cmd = self.command + ["jobqueue", "view", "-i"] + shlex.split(job)

        result = subprocess.run(_cmd, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout = result.stdout

        if result.returncode != 0:
            raise RuntimeError(result.stderr)

        start_index = stdout.find("---------------------------- JOB -------------------------") + len(
            "---------------------------- JOB -------------------------"
        )
        end_index = stdout.find("----------------------------------------------------------")

        job_info = stdout[start_index:end_index].strip()
        lines = job_info.split("\n")

        for line in lines:
            line = line.strip()
            line = line.replace("[", "").replace("]", "")
            if "=" in line:
                key, value = line.split("=", 1)
                job_dict[key.strip()] = value.strip()

        return job_dict

    def jobqueue_status(self, job: str) -> str:
        result = self.jobqueue_view(job)
        status = result["Status"]
        return status

    def jobqueue_wait(self, job: str) -> str:
        status = self.jobqueue_status(job)
        while status == "Running" or status == "In Progress":
            time.sleep(1)
            status = self.jobqueue_status(job)

        return status

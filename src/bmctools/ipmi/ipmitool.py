from datetime import datetime
from bmctools.misc import is_older_than_unit
import subprocess
import shlex
from typing import Optional, Union


class IpmiTool:
    """
    Simple Ipmitool wrapper. Requires ipmitool to be installed and available as a shell command.
    ipmi_command() can use used to run arbitrary ipmi commands and additional functions are added for common operations.
    NOTE: Currently, these will not run directly on stackstorm k8s, must be run through toolbox action.

    Sample Usage:
    mynode = IpmiTool(10.206.137.50, admin, mypassword)
    sel_list = mynode.get_sel_list()

    With server object:

    mynode = Server(mapi, uuid)
    mynode.ipmitool.power_status()

    """

    def __init__(self, host: str, user: str, password: str):
        self.host = host
        self.user = user
        self.password = password


    def ipmitool_command(self, command: str) -> str:
        """
        Execute arbitary ipmitool command.
        """
        cmd = [
            "ipmitool",
            "-H",
            shlex.quote(self.host),
            "-U",
            shlex.quote(self.user),
            "-P",
            shlex.quote(self.password),
            "-I",
            "lanplus",
        ] + shlex.split(command)
        try:
            return subprocess.run(
                cmd, shell=False, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8"
            ).stdout
        except subprocess.CalledProcessError as e:
            raise RuntimeError(e.stderr)


    def power_status(self) -> str:
        return self.ipmitool_command("power status")


    def power_off(self) -> str:
        return self.ipmitool_command("power off")


    def power_on(self) -> str:
        return self.ipmitool_command("power on")


    def power_reset(self) -> str:
        return self.ipmitool_command("power reset")


    def bmc_reset_warm(self) -> str:
        return self.ipmitool_command("mc reset warm")


    def bmc_reset_cold(self) -> str:
        return self.ipmitool_command("mc reset cold")


    def sel_list(
        self, elist: Optional[bool] = False, raw: Optional[bool] = False, age: Optional[bool] = None
    ) -> Union[list, bool]:
        if raw and age:
            raise ValueError("raw with age argument is not supported.")

        if elist:
            results = self.ipmitool_command("sel elist")
        else:
            results = self.ipmitool_command("sel list")

        if raw:
            return results

        results_exist = results.strip()

        if results_exist:
            lines = [line.split(" | ") for line in results.strip().split("\n")]
            keys = ["ID", "Date", "Time", "Event", "Description", "Status"]
            dict_results = [dict(zip(keys, line)) for line in lines]

            if age:
                age_length = int(age[:-1])
                age_unit = age[-1]
                input_format = "%m/%d/%Y %H:%M:%S"
                output_format = "%Y-%m-%d %H:%M:%S"
                recent_events = []
                for entry in dict_results:
                    date = entry["Date"]
                    time = entry["Time"].rsplit(maxsplit=1)[0]
                    try:
                        dt_obj = datetime.strptime(f"{date} {time}", input_format)
                        converted = dt_obj.strftime(output_format)
                        if not is_older_than_unit(converted, age_length, age_unit):
                            recent_events.append(entry)
                    except ValueError:
                        # include entries without timestamps
                        recent_events.append(entry)
                return recent_events
            else:
                return dict_results
        else:
            return False


    def sol_deactivate(self) -> str:
        return self.ipmitool_command("sol deactivate")


    def sol_looptest(self, num_loops: Optional[int] = 1):
        if isinstance(num_loops, int):
            return self.ipmitool_command(f"sol looptest {num_loops}")
        else:
            raise TypeError("num_loops must be of type int")

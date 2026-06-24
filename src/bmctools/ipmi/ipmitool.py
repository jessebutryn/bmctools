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

    INTERFACES = ["lanplus", "lan"]
    CIPHER_SUITES = [None, 17, 3, 1]

    def __init__(self, host: str, user: str, password: str):
        self.host = host
        self.user = user
        self.password = password
        self._interface: Optional[str] = None
        self._cipher_suite: Optional[int] = None


    def _build_cmd(self, command: str, interface: str, cipher_suite: Optional[int] = None) -> list:
        """Build the ipmitool command list.

        Connection values (host/user/password) are passed verbatim. They must
        NOT be run through ``shlex.quote``: the command is executed with
        ``shell=False``, so there is no shell to strip the quotes ``shlex.quote``
        adds. Quoting a password containing shell metacharacters (e.g. ``@#$``)
        would otherwise embed literal quotes into the credential ipmitool
        receives, breaking authentication and inflating the byte length past the
        16-byte IPMI v1.5 limit.
        """
        cmd = [
            "ipmitool",
            "-H", self.host,
            "-U", self.user,
            "-P", self.password,
            "-I", interface,
        ]
        if cipher_suite is not None:
            cmd += ["-C", str(cipher_suite)]
        return cmd + shlex.split(command)


    def ipmitool_command(self, command: str) -> str:
        """Execute arbitrary ipmitool command.

        On the first call, tries all interface/cipher suite combinations
        and caches the working combination for subsequent calls.
        """
        if self._interface is not None:
            cmd = self._build_cmd(command, self._interface, self._cipher_suite)
            try:
                return subprocess.run(
                    cmd, shell=False, check=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8"
                ).stdout
            except subprocess.CalledProcessError as e:
                raise RuntimeError(e.stderr)

        last_error = None
        for interface in self.INTERFACES:
            for cipher_suite in self.CIPHER_SUITES:
                cmd = self._build_cmd(command, interface, cipher_suite)
                try:
                    result = subprocess.run(
                        cmd, shell=False, check=True,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8"
                    ).stdout
                    self._interface = interface
                    self._cipher_suite = cipher_suite
                    return result
                except subprocess.CalledProcessError as e:
                    last_error = e.stderr

        raise RuntimeError(last_error)


    def power_status(self) -> str:
        """Get the current power status of the system.

        Returns:
            String output from ipmitool (e.g., 'Chassis Power is on').
        """
        return self.ipmitool_command("power status")


    def power_off(self) -> str:
        """Issue a hard power-off command.

        Returns:
            String output from ipmitool.
        """
        return self.ipmitool_command("power off")


    def power_on(self) -> str:
        """Issue a power-on command.

        Returns:
            String output from ipmitool.
        """
        return self.ipmitool_command("power on")


    def power_reset(self) -> str:
        """Issue a hard power-reset command.

        ``power reset`` only works when the system is already on. If the system
        is off, the intent behind a reset is still to bring the machine up, so
        a power-on is issued instead.

        Returns:
            String output from ipmitool.
        """
        if "on" in self.power_status().lower():
            return self.ipmitool_command("power reset")
        return self.power_on()


    def power_cycle(self) -> str:
        """Issue a power-cycle command (cold reboot).

        ``power cycle`` powers the system off and then back on. As with
        ``power reset``, it only works when the system is already on, so if the
        system is off a power-on is issued instead.

        Returns:
            String output from ipmitool.
        """
        if "on" in self.power_status().lower():
            return self.ipmitool_command("power cycle")
        return self.power_on()


    def bmc_reset_warm(self) -> str:
        """Perform a warm reset of the BMC controller.

        Returns:
            String output from ipmitool.
        """
        return self.ipmitool_command("mc reset warm")


    def bmc_reset_cold(self) -> str:
        """Perform a cold reset of the BMC controller.

        Returns:
            String output from ipmitool.
        """
        return self.ipmitool_command("mc reset cold")


    def sel_list(
        self, elist: Optional[bool] = False, raw: Optional[bool] = False, age: Optional[bool] = None
    ) -> Union[list, bool]:
        """Retrieve the System Event Log (SEL).

        Args:
            elist: If True, use extended list format (``sel elist``) for richer event details.
            raw: If True, return the raw string output instead of a parsed list.
            age: Filter events newer than this age string (e.g., '30d', '12h', '2h').
                 Cannot be combined with ``raw``.

        Returns:
            Parsed list of event dicts, raw string (if ``raw=True``), or ``False`` if the
            log is empty.

        Raises:
            ValueError: If both ``raw`` and ``age`` are specified.
        """
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
        """Deactivate an active Serial Over LAN (SOL) session.

        Returns:
            String output from ipmitool.
        """
        return self.ipmitool_command("sol deactivate")


    def sol_looptest(self, num_loops: Optional[int] = 1) -> str:
        """Run a Serial Over LAN loopback test.

        Args:
            num_loops: Number of loopback iterations to run (default: 1).

        Returns:
            String output from ipmitool.

        Raises:
            TypeError: If ``num_loops`` is not an integer.
        """
        if isinstance(num_loops, int):
            return self.ipmitool_command(f"sol looptest {num_loops}")
        else:
            raise TypeError("num_loops must be of type int")

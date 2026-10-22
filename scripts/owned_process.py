"""Kill-on-close ownership of execution and interpreter descendants."""
import asyncio
import os
import signal


class ProcessOwner:
    def __init__(self, pid):
        self.pid = pid
        self.job = None
        if os.name == "nt":
            import win32api, win32con, win32job
            self.job = win32job.CreateJobObject(None, "")
            info = win32job.QueryInformationJobObject(self.job, win32job.JobObjectExtendedLimitInformation)
            info["BasicLimitInformation"]["LimitFlags"] = (
                win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE |
                win32job.JOB_OBJECT_LIMIT_PROCESS_MEMORY)
            info["ProcessMemoryLimit"] = 512 * 1024 * 1024
            win32job.SetInformationJobObject(self.job, win32job.JobObjectExtendedLimitInformation, info)
            process = win32api.OpenProcess(win32con.PROCESS_SET_QUOTA | win32con.PROCESS_TERMINATE, False, pid)
            try:
                win32job.AssignProcessToJobObject(self.job, process)
            except BaseException:
                self.job.Close()
                self.job = None
                raise
            finally:
                process.Close()

    def close(self):
        if self.job is not None:
            self.job.Close()
            self.job = None
        elif os.name != "nt":
            try:
                os.killpg(self.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def subprocess_options():
    return {"creationflags": 0x08000000} if os.name == "nt" else {"start_new_session": True}


async def terminate_owned(process, owner):
    if owner:
        owner.close()
    elif process.returncode is None:
        process.kill()
    await process.wait()

"""Process cleanup manager for SDR processes

This module provides centralized process management to prevent orphaned rtl_fm,
rtl_scan_2.py, and rtl_scan_live.py processes.

PROBLEM: 
- rtl_fm processes not being killed properly
- Multiple processes accumulating
- SDR device locked by zombie processes

SOLUTION:
- Track ALL processes in a central registry
- Kill processes with SIGTERM then SIGKILL if needed
- Cleanup on mode switches and logout
"""

import subprocess
import signal
import os
import time


class ProcessManager:
    """Centralized manager for all SDR-related subprocesses"""
    
    def __init__(self):
        # Registry of all active processes
        # Format: {name: process_object}
        self.processes = {}
        
    def start_process(self, name, command, **popen_kwargs):
        """
        Start a new process and register it
        
        Args:
            name: Unique identifier for this process (e.g., 'demodulator', 'scanner', 'waterfall')
            command: Command to execute (list or string)
            **popen_kwargs: Additional arguments for subprocess.Popen
            
        Returns:
            subprocess.Popen object
        """
        # Kill any existing process with this name first
        self.kill_process(name)
        
        # Start new process
        if isinstance(command, str):
            # String command - use shell
            process = subprocess.Popen(
                command,
                shell=True,
                preexec_fn=os.setsid,  # Create new process group
                **popen_kwargs
            )
        else:
            # List command
            process = subprocess.Popen(
                command,
                preexec_fn=os.setsid,  # Create new process group
                **popen_kwargs
            )
        
        # Register the process
        self.processes[name] = process
        print("ProcessManager: Started '{}' (PID: {})".format(name, process.pid))
        
        return process
    
    def kill_process(self, name, timeout=2.0):
        """
        Kill a specific process by name
        
        Args:
            name: Process identifier
            timeout: Seconds to wait for graceful shutdown before SIGKILL
            
        Returns:
            bool: True if process was killed, False if not found
        """
        if name not in self.processes:
            return False
        
        process = self.processes[name]
        
        # Check if already dead
        if process.poll() is not None:
            print("ProcessManager: '{}' already terminated".format(name))
            del self.processes[name]
            return True
        
        try:
            print("ProcessManager: Killing '{}' (PID: {})...".format(name, process.pid))
            
            # Try graceful shutdown first (SIGTERM)
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            
            # Wait for graceful shutdown
            start_time = time.time()
            while process.poll() is None and (time.time() - start_time) < timeout:
                time.sleep(0.1)
            
            # If still alive, force kill (SIGKILL)
            if process.poll() is None:
                print("ProcessManager: '{}' did not respond to SIGTERM, using SIGKILL".format(name))
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                process.wait()  # Wait for it to die
            
            print("ProcessManager: '{}' terminated successfully".format(name))
            
        except (OSError, ProcessLookupError) as e:
            print("ProcessManager: Error killing '{}': {}".format(name, e))
        
        finally:
            # Remove from registry
            del self.processes[name]
        
        return True
    
    def kill_all(self, timeout=2.0):
        """
        Kill all registered processes
        
        Args:
            timeout: Seconds to wait for each process to terminate gracefully
        """
        print("ProcessManager: Killing all processes...")
        
        # Get list of names (make copy since we'll be modifying the dict)
        process_names = list(self.processes.keys())
        
        for name in process_names:
            self.kill_process(name, timeout=timeout)
        
        print("ProcessManager: All processes terminated")
    
    def is_running(self, name):
        """
        Check if a process is still running
        
        Args:
            name: Process identifier
            
        Returns:
            bool: True if running, False otherwise
        """
        if name not in self.processes:
            return False
        
        process = self.processes[name]
        return process.poll() is None
    
    def get_process(self, name):
        """
        Get a process object by name
        
        Args:
            name: Process identifier
            
        Returns:
            subprocess.Popen object or None
        """
        return self.processes.get(name)
    
    def cleanup_dead_processes(self):
        """Remove processes that have already terminated from registry"""
        dead_processes = []
        
        for name, process in self.processes.items():
            if process.poll() is not None:
                dead_processes.append(name)
        
        for name in dead_processes:
            print("ProcessManager: Cleaning up dead process '{}'".format(name))
            del self.processes[name]
    
    def list_processes(self):
        """
        Get list of all registered processes
        
        Returns:
            dict: {name: (pid, status)}
        """
        self.cleanup_dead_processes()
        
        result = {}
        for name, process in self.processes.items():
            status = "running" if process.poll() is None else "terminated"
            result[name] = (process.pid, status)
        
        return result
    
    def __del__(self):
        """Cleanup on destruction"""
        self.kill_all(timeout=1.0)


# Global singleton instance
_process_manager = None

def get_process_manager():
    """Get the global ProcessManager singleton"""
    global _process_manager
    if _process_manager is None:
        _process_manager = ProcessManager()
    return _process_manager

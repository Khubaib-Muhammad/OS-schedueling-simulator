import multiprocessing
import threading
import time
import random
from typing import List, Dict

# =====================================================================
# 1. CONCURRENCY WORKERS & IPC DEMONSTRATION
# =====================================================================

def thread_worker(pid: int, pipe_conn, shared_stats: dict):
    """
    Simulates a process using a thread.
    IPC Techniques Used: 
    - Pipe (for direct scheduler commands)
    - Shared Memory (via a shared dictionary)
    """
    # Initialize in shared memory
    shared_stats[pid] = {'status': 'INITIALIZED', 'executed_time': 0}
    
    while True:
        # Wait for scheduler to give a time slice (Pipe)
        msg = pipe_conn.recv()
        
        if msg['cmd'] == 'TERMINATE':
            shared_stats[pid]['status'] = 'TERMINATED'
            break
        elif msg['cmd'] == 'EXECUTE':
            slice_duration = msg['duration']
            
            # Simulate actual work (CPU Burst)
            # If IO bound, we randomly yield before slice ends
            if msg.get('is_io') and slice_duration > 2:
                actual_run = random.uniform(1, slice_duration - 1)
                time.sleep(actual_run / 1000.0)
                shared_stats[pid]['executed_time'] += actual_run
                shared_stats[pid]['status'] = 'WAITING_IO'
                pipe_conn.send({'status': 'YIELD', 'pid': pid, 'executed': actual_run})
            else:
                time.sleep(slice_duration / 1000.0) 
                shared_stats[pid]['executed_time'] += slice_duration
                shared_stats[pid]['status'] = 'WAITING'
                pipe_conn.send({'status': 'DONE', 'pid': pid, 'executed': slice_duration})

def process_worker(pid: int, pipe_conn, queue: multiprocessing.Queue):
    """
    Simulates a process using a separate OS process (fork/spawn).
    IPC Techniques Used:
    - Pipe (for direct scheduler commands)
    - Message Queue (for broadcasting statistics)
    """
    import os
    actual_pid = os.getpid()
    
    # Broadcast initialization (Message Queue)
    queue.put({'type': 'INIT', 'sim_pid': pid, 'os_pid': actual_pid})
    
    executed_time = 0
    while True:
        # Wait for scheduler command (Pipe)
        msg = pipe_conn.recv()
        
        if msg['cmd'] == 'TERMINATE':
            queue.put({'type': 'STAT', 'sim_pid': pid, 'status': 'TERMINATED', 'total_time': executed_time})
            break
        elif msg['cmd'] == 'EXECUTE':
            slice_duration = msg['duration']
            
            # Simulate actual work (CPU Burst)
            if msg.get('is_io') and slice_duration > 2:
                import random
                actual_run = random.uniform(1, slice_duration - 1)
                time.sleep(actual_run / 1000.0) 
                executed_time += actual_run
                pipe_conn.send({'status': 'YIELD', 'pid': pid, 'executed': actual_run})
                queue.put({'type': 'STAT', 'sim_pid': pid, 'status': 'WAITING_IO', 'executed_time': executed_time})
            else:
                time.sleep(slice_duration / 1000.0) 
                executed_time += slice_duration
                pipe_conn.send({'status': 'DONE', 'pid': pid, 'executed': slice_duration})
                queue.put({'type': 'STAT', 'sim_pid': pid, 'status': 'WAITING', 'executed_time': executed_time})


# =====================================================================
# 2. CONCURRENCY EXPERIMENT RUNNER
# =====================================================================

class ConcurrencyExperimentRunner:
    """
    Runs simulated processes under both Threading and Multiprocessing
    paradigms to calculate Context Switching Overhead and Execution Speed.
    """
    def __init__(self, workloads: List[Dict], quantum: int = 10):
        self.workloads = workloads  # List of dicts: {'pid': 1, 'burst': 50}
        self.quantum = quantum
        
    def run_threaded(self) -> Dict:
        start_wall_time = time.time()
        
        pipes = {}
        threads = []
        shared_stats = {}  # Shared memory approach
        
        # 1. Spawn Threads
        for p in self.workloads:
            parent_conn, child_conn = multiprocessing.Pipe()
            pipes[p['pid']] = parent_conn
            
            t = threading.Thread(target=thread_worker, args=(p['pid'], child_conn, shared_stats))
            t.start()
            threads.append(t)
            
        # 2. Orchestrate Execution
        switches, total_burst = self._orchestrate_scheduling(pipes)
        
        # 3. Terminate
        for pid, pipe in pipes.items():
            pipe.send({'cmd': 'TERMINATE'})
        for t in threads:
            t.join()
            
        end_wall_time = time.time()
        wall_duration = (end_wall_time - start_wall_time) * 1000 # to ms
        overhead = wall_duration - total_burst
        
        return {
            'mode': 'Threading',
            'processes': len(self.workloads),
            'total_burst_ms': total_burst,
            'wall_clock_ms': round(wall_duration, 2),
            'context_switches': switches,
            'context_switch_overhead_ms': round(max(0, overhead), 2),
            'avg_overhead_per_switch_ms': round(max(0, overhead) / max(1, switches), 4)
        }
        
    def run_multiprocessing(self) -> Dict:
        start_wall_time = time.time()
        
        pipes = {}
        processes = []
        msg_queue = multiprocessing.Queue()
        
        # 1. Spawn Processes
        for p in self.workloads:
            parent_conn, child_conn = multiprocessing.Pipe()
            pipes[p['pid']] = parent_conn
            
            proc = multiprocessing.Process(target=process_worker, args=(p['pid'], child_conn, msg_queue))
            proc.start()
            processes.append(proc)
            
        # 2. Orchestrate Execution
        switches, total_burst = self._orchestrate_scheduling(pipes)
        
        # 3. Terminate and Drain Queue safely before joining to prevent deadlocks
        for pid, pipe in pipes.items():
            pipe.send({'cmd': 'TERMINATE'})
            
        # Keep draining queue until all worker processes have exited
        import queue
        alive = True
        while alive:
            alive = False
            for proc in processes:
                if proc.is_alive():
                    alive = True
            
            # Non-blockingly drain the queue
            while not msg_queue.empty():
                try:
                    msg_queue.get_nowait()
                except queue.Empty:
                    break
                except:
                    break
            
            if alive:
                time.sleep(0.001)
                
        # Final post-execution drain
        while not msg_queue.empty():
            try:
                msg_queue.get_nowait()
            except queue.Empty:
                break
            except:
                break
                
        # Safe to join now
        for proc in processes:
            proc.join()
            
        end_wall_time = time.time()
        wall_duration = (end_wall_time - start_wall_time) * 1000
        overhead = wall_duration - total_burst
        
        return {
            'mode': 'Multiprocessing (fork/spawn)',
            'processes': len(self.workloads),
            'total_burst_ms': total_burst,
            'wall_clock_ms': round(wall_duration, 2),
            'context_switches': switches,
            'context_switch_overhead_ms': round(max(0, overhead), 2),
            'avg_overhead_per_switch_ms': round(max(0, overhead) / max(1, switches), 4)
        }

    def _orchestrate_scheduling(self, pipes: Dict) -> tuple:
        """
        Runs a Round Robin scheduler, sending EXECUTE commands via Pipes.
        Returns: (context_switch_count, total_burst_executed)
        """
        remaining = {p['pid']: p['burst'] for p in self.workloads}
        total_burst = sum(remaining.values())
        context_switches = 0
        
        while sum(remaining.values()) > 0.01:
            for pid, pipe in pipes.items():
                if remaining[pid] > 0.01:
                    context_switches += 1
                    slice_duration = min(self.quantum, remaining[pid])
                    remaining[pid] = round(remaining[pid] - slice_duration, 2)
                    
                    # IPC Communication: Issue Command
                    is_io = next((w.get('is_io', False) for w in self.workloads if w['pid'] == pid), False)
                    pipe.send({'cmd': 'EXECUTE', 'duration': slice_duration, 'is_io': is_io})
                    
                    # IPC Communication: Wait for Acknowledgement
                    resp = pipe.recv()
                    actual_executed = resp.get('executed', slice_duration)
                    
                    # Fix remaining time based on actual executed time
                    # We subtract actual_executed instead of slice_duration because it might have yielded early
                    remaining[pid] = round(remaining[pid] + slice_duration - actual_executed, 2)
                    
        return context_switches, total_burst

if __name__ == "__main__":
    # Quick Test
    import random
    print("Running Concurrency Test...")
    workloads = [{'pid': i, 'burst': 50, 'is_io': random.choice([True, False])} for i in range(1, 11)]
    runner = ConcurrencyExperimentRunner(workloads, quantum=10)
    
    print(runner.run_threaded())
    print(runner.run_multiprocessing())

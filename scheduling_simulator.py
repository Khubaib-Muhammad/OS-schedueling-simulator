import tkinter as tk
from tkinter import ttk, messagebox
from typing import List, Dict, Optional
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
import random

# Robust Matplotlib imports for Phase 3 Slate-Dark Analytics
try:
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False


class ProcessState(Enum):
    """Process State Enumeration"""
    NEW = "New"
    READY = "Ready"
    RUNNING = "Running"
    WAITING = "Waiting"
    TERMINATED = "Terminated"


@dataclass
class Process:
    """
    Process Data Class
    Represents a process in the scheduling simulator
    """
    pid: int
    name: str
    arrival_time: int
    burst_time: int
    memory_required: int = 100
    priority: int = 0
    remaining_burst: int = 0
    waiting_time: int = 0
    turnaround_time: int = 0
    completion_time: int = 0
    start_time: int = -1
    state: ProcessState = ProcessState.NEW
    is_io_bound: bool = False
    io_duration: int = 0
    # Next-Gen scheduling fields
    nice: int = 0
    vruntime: float = 0.0
    deadline: int = 0
    period: int = 0
    # New detailed tracking fields
    response_time: int = -1  # Time from arrival to first execution
    first_start_time: int = -1  # When process first started
    cpu_burst_history: list = field(default_factory=list)  # List of CPU bursts
    state_history: list = field(default_factory=list)  # List of (time, state) tuples
    execution_log: list = field(default_factory=list)  # Detailed execution log
    
    def __post_init__(self):
        self.remaining_burst = self.burst_time
    
    def to_dict(self) -> Dict:
        return {
            'pid': self.pid,
            'name': self.name,
            'arrival_time': self.arrival_time,
            'burst_time': self.burst_time,
            'memory_required': self.memory_required,
            'priority': self.priority,
            'remaining_burst': self.remaining_burst,
            'waiting_time': self.waiting_time,
            'turnaround_time': self.turnaround_time,
            'completion_time': self.completion_time,
            'state': self.state.value,
            'is_io_bound': self.is_io_bound,
            'nice': self.nice,
            'period': self.period,
            'deadline': self.deadline
        }


class MemoryAllocationAlgorithm(Enum):
    FIRST_FIT = "First Fit"
    BEST_FIT = "Best Fit"
    WORST_FIT = "Worst Fit"


class PageReplacementAlgorithm(Enum):
    FIFO = "FIFO"
    LRU = "LRU"


@dataclass
class PageTableEntry:
    page_number: int
    frame_number: Optional[int] = None
    is_present: bool = False
    last_accessed: float = 0.0
    swap_offset: Optional[int] = None


@dataclass
class MemoryBlock:
    start_address: int
    size: int
    process_pid: Optional[int] = None
    
    @property
    def is_free(self) -> bool:
        return self.process_pid is None


class MemoryManager:
    def __init__(self, total_memory: int = 1024):
        self.total_memory = total_memory
        self.blocks = [MemoryBlock(0, total_memory)]
        self.algorithm = MemoryAllocationAlgorithm.FIRST_FIT
        
        # Virtual Memory Paging variables
        self.paging_enabled = False  # Set to False by default for backward-compatibility with contiguous tests
        self.page_size = 64  # Default Page Size: 64 MB
        self.replacement_algorithm = PageReplacementAlgorithm.FIFO
        self.simulator = None
        
        self.frames: List[Optional[Dict]] = []
        self.swap_space: Dict[int, Dict] = {}
        self.fifo_queue: List[tuple] = []  # List of (pid, page_number)
        self.page_faults: Dict[int, int] = {}  # pid -> fault_count
        self.total_page_faults = 0
        self.page_fault_penalty = 2  # Time penalty for page fault in simulation steps
        self.events: List[str] = []
        self.reset_paging()

    def reset_paging(self):
        num_frames = self.total_memory // self.page_size
        self.frames = [None] * num_frames
        self.swap_space = {}
        self.fifo_queue = []
        self.page_faults = {}
        self.total_page_faults = 0
        self.events = []

    def reset(self, total_memory: Optional[int] = None):
        if total_memory is not None:
            self.total_memory = total_memory
        self.blocks = [MemoryBlock(0, self.total_memory)]
        self.reset_paging()

    @property
    def allocated_memory(self) -> int:
        if not self.paging_enabled:
            return self.total_memory - sum(b.size for b in self.blocks if b.is_free)
        else:
            allocated_frames = sum(1 for f in self.frames if f is not None)
            return allocated_frames * self.page_size

    def allocate(self, process: Process) -> bool:
        if not self.paging_enabled:
            if process.memory_required > self.total_memory:
                return False
                
            free_blocks = [b for b in self.blocks if b.is_free and b.size >= process.memory_required]
            if not free_blocks:
                return False
                
            selected_block = None
            if self.algorithm == MemoryAllocationAlgorithm.FIRST_FIT:
                selected_block = free_blocks[0]
            elif self.algorithm == MemoryAllocationAlgorithm.BEST_FIT:
                selected_block = min(free_blocks, key=lambda b: b.size)
            elif self.algorithm == MemoryAllocationAlgorithm.WORST_FIT:
                selected_block = max(free_blocks, key=lambda b: b.size)
                
            if selected_block:
                if selected_block.size > process.memory_required:
                    new_block = MemoryBlock(
                        selected_block.start_address + process.memory_required,
                        selected_block.size - process.memory_required
                    )
                    idx = self.blocks.index(selected_block)
                    self.blocks.insert(idx + 1, new_block)
                    
                selected_block.size = process.memory_required
                selected_block.process_pid = process.pid
                self.events.append(f"[{process.name}] allocated {process.memory_required}MB RAM (contiguous)")
                return True
            return False
        else:
            # Virtual Memory Paging path
            import math
            num_pages = math.ceil(process.memory_required / self.page_size)
            process.page_table = {}
            for p in range(num_pages):
                process.page_table[p] = PageTableEntry(page_number=p, is_present=False)
            
            self.page_faults[process.pid] = 0
            self.events.append(f"[{process.name}] created {num_pages} virtual memory pages")
            
            # Demand paging warm start
            self.load_page_into_ram(process, 0, current_time=0.0)
            return True

    def deallocate(self, pid: int):
        self.events.append(f"[PID {pid}] released memory resources")
        if not self.paging_enabled:
            for block in self.blocks:
                if block.process_pid == pid:
                    block.process_pid = None
            self._merge_free_blocks()
        else:
            for idx in range(len(self.frames)):
                if self.frames[idx] and self.frames[idx]['pid'] == pid:
                    self.frames[idx] = None
            
            swap_slots_to_delete = [slot for slot, frame in self.swap_space.items() if frame['pid'] == pid]
            for slot in swap_slots_to_delete:
                del self.swap_space[slot]
                
            self.fifo_queue = [item for item in self.fifo_queue if item[0] != pid]

    def _merge_free_blocks(self):
        merged = []
        for block in self.blocks:
            if merged and merged[-1].is_free and block.is_free:
                merged[-1].size += block.size
            else:
                merged.append(block)
        self.blocks = merged

    def get_fragmentation(self) -> int:
        if not self.paging_enabled:
            free_blocks = [b.size for b in self.blocks if b.is_free]
            if len(free_blocks) <= 1:
                return 0
            return sum(free_blocks) - max(free_blocks)
        else:
            return 0  # Paging completely eliminates external fragmentation!

    def access_page(self, process: Process, page_number: int, current_time: float) -> bool:
        if not self.paging_enabled or not hasattr(process, 'page_table') or not process.page_table:
            return True
            
        entry = process.page_table.get(page_number)
        if not entry:
            return True
            
        if entry.is_present:
            entry.last_accessed = current_time
            return True
            
        self.page_faults[process.pid] = self.page_faults.get(process.pid, 0) + 1
        self.total_page_faults += 1
        
        self.load_page_into_ram(process, page_number, current_time)
        return False

    def load_page_into_ram(self, process: Process, page_number: int, current_time: float) -> bool:
        entry = process.page_table.get(page_number)
        if not entry:
            return False
            
        if entry.is_present:
            entry.last_accessed = current_time
            return True
            
        free_frame_idx = None
        for idx, frame in enumerate(self.frames):
            if frame is None:
                free_frame_idx = idx
                break
                
        if free_frame_idx is None:
            free_frame_idx = self.evict_page(current_time)
            
        self.frames[free_frame_idx] = {'pid': process.pid, 'page': page_number}
        entry.frame_number = free_frame_idx
        entry.is_present = True
        entry.last_accessed = current_time
        
        if entry.swap_offset in self.swap_space:
            self.events.append(f"[{process.name}] Swap-In: loaded page {page_number} to frame {free_frame_idx} from swap")
            del self.swap_space[entry.swap_offset]
            entry.swap_offset = None
        else:
            self.events.append(f"[{process.name}] Loaded page {page_number} to frame {free_frame_idx}")
            
        self.fifo_queue.append((process.pid, page_number))
        return True

    def evict_page(self, current_time: float) -> int:
        if self.replacement_algorithm == PageReplacementAlgorithm.FIFO:
            while self.fifo_queue:
                pid, page_number = self.fifo_queue.pop(0)
                proc = self._get_process_by_pid(pid)
                if proc and hasattr(proc, 'page_table') and page_number in proc.page_table:
                    entry = proc.page_table[page_number]
                    if entry.is_present:
                        frame_idx = entry.frame_number
                        entry.is_present = False
                        entry.frame_number = None
                        
                        swap_slot = self._get_free_swap_slot()
                        self.swap_space[swap_slot] = {'pid': pid, 'page': page_number}
                        entry.swap_offset = swap_slot
                        
                        self.events.append(f"[{proc.name}] Page Fault! Evicted page {page_number} to swap slot {swap_slot} (FIFO)")
                        self.frames[frame_idx] = None
                        return frame_idx
            return 0
        else: # LRU
            oldest_time = float('inf')
            victim_pid = None
            victim_page = None
            victim_frame = None
            
            for frame_idx, frame in enumerate(self.frames):
                if frame is not None:
                    proc = self._get_process_by_pid(frame['pid'])
                    if proc and hasattr(proc, 'page_table') and frame['page'] in proc.page_table:
                        entry = proc.page_table[frame['page']]
                        if entry.last_accessed < oldest_time:
                            oldest_time = entry.last_accessed
                            victim_pid = frame['pid']
                            victim_page = frame['page']
                            victim_frame = frame_idx
                            
            if victim_frame is not None:
                proc = self._get_process_by_pid(victim_pid)
                entry = proc.page_table[victim_page]
                entry.is_present = False
                entry.frame_number = None
                
                swap_slot = self._get_free_swap_slot()
                self.swap_space[swap_slot] = {'pid': victim_pid, 'page': victim_page}
                entry.swap_offset = swap_slot
                
                self.events.append(f"[{proc.name}] Page Fault! Evicted page {victim_page} to swap slot {swap_slot} (LRU)")
                self.fifo_queue = [item for item in self.fifo_queue if item != (victim_pid, victim_page)]
                self.frames[victim_frame] = None
                return victim_frame
            return 0

    def _get_process_by_pid(self, pid: int) -> Optional[Process]:
        if self.simulator and hasattr(self.simulator, 'processes'):
            for p in self.simulator.processes:
                if p.pid == pid:
                    return p
        return None

    def _get_free_swap_slot(self) -> int:
        slot = 0
        while slot in self.swap_space:
            slot += 1
        return slot


class SchedulingAlgorithm(Enum):
    """Scheduling Algorithm Enumeration"""
    FCFS = "First-Come, First-Served"
    SJF = "Shortest Job First"
    PRIORITY = "Priority Scheduling"
    ROUND_ROBIN = "Round Robin"
    MLFQ = "Multilevel Feedback Queue"
    CFS = "Completely Fair Scheduler (CFS)"
    RMS = "Rate Monotonic Scheduling (RMS)"
    EDF = "Earliest Deadline First (EDF)"
class BaseScheduler:
    """
    Base Scheduler Class
    Abstract base class for all scheduling algorithms
    """
    
    def __init__(self, name: str):
        self.name = name
        self.ready_queue: List[Process] = []
        self.completed_processes: List[Process] = []
        self.current_time = 0
        self.is_preemptive = False
        
    def add_process(self, process: Process):
        """Add a process to the ready queue"""
        process.state = ProcessState.READY
        self.ready_queue.append(process)
        
    def get_next_process(self) -> Optional[Process]:
        """Get the next process to execute - to be implemented by subclasses"""
        raise NotImplementedError
    
    def update_process_times(self, current_process: Process, time_slice: int):
        """Update waiting and turnaround times for all processes"""
        for p in self.ready_queue:
            if p.pid != current_process.pid and p.state == ProcessState.READY:
                p.waiting_time += time_slice
    
    def calculate_metrics(self) -> Dict:
        """Calculate performance metrics"""
        if not self.completed_processes:
            return {
                'avg_waiting_time': 0,
                'avg_turnaround_time': 0,
                'cpu_utilization': 0,
                'throughput': 0,
                'completed_count': 0
            }
        
        n = len(self.completed_processes)
        total_waiting = sum(p.waiting_time for p in self.completed_processes)
        total_turnaround = sum(p.turnaround_time for p in self.completed_processes)
        
        # CPU Utilization calculation
        total_burst = sum(p.burst_time for p in self.completed_processes)
        max_time = max(p.completion_time for p in self.completed_processes)
        cpu_util = (total_burst / max_time * 100) if max_time > 0 else 0
        
        # Throughput (processes per unit time)
        throughput = n / max_time if max_time > 0 else 0
        
        return {
            'avg_waiting_time': total_waiting / n,
            'avg_turnaround_time': total_turnaround / n,
            'cpu_utilization': cpu_util,
            'throughput': throughput,
            'completed_count': n
        }
    
    def reset(self):
        """Reset the scheduler"""
        self.ready_queue = []
        self.completed_processes = []
        self.current_time = 0


class FCFSScheduler(BaseScheduler):
    """First-Come, First-Served Scheduler"""
    
    def __init__(self):
        super().__init__("FCFS")
        self.is_preemptive = False
    
    def add_process(self, process: Process):
        process.state = ProcessState.READY
        self.ready_queue.append(process)
        # Sort by arrival time
        self.ready_queue.sort(key=lambda p: p.arrival_time)
    
    def get_next_process(self) -> Optional[Process]:
        if not self.ready_queue:
            return None
        # FCFS: return the first process that has arrived
        for p in self.ready_queue:
            if p.arrival_time <= self.current_time:
                self.ready_queue.remove(p)
                return p
        return None


class SJFScheduler(BaseScheduler):
    """Shortest Job First Scheduler"""
    
    def __init__(self, preemptive: bool = False):
        super().__init__("SJF" + (" (Preemptive)" if preemptive else " (Non-Preemptive)"))
        self.is_preemptive = preemptive
    
    def add_process(self, process: Process):
        process.state = ProcessState.READY
        self.ready_queue.append(process)
        # Sort by burst time
        self.ready_queue.sort(key=lambda p: p.remaining_burst)
    
    def get_next_process(self) -> Optional[Process]:
        if not self.ready_queue:
            return None
        # Find shortest job that has arrived
        available = [p for p in self.ready_queue if p.arrival_time <= self.current_time]
        if not available:
            return None
        available.sort(key=lambda p: p.remaining_burst)
        process = available[0]
        self.ready_queue.remove(process)
        return process


class PriorityScheduler(BaseScheduler):
    """Priority Scheduling Scheduler"""
    
    def __init__(self, preemptive: bool = False):
        super().__init__("Priority" + (" (Preemptive)" if preemptive else " (Non-Preemptive)"))
        self.is_preemptive = preemptive
    
    def add_process(self, process: Process):
        process.state = ProcessState.READY
        self.ready_queue.append(process)
        # Sort by priority (lower number = higher priority)
        self.ready_queue.sort(key=lambda p: p.priority)
    
    def get_next_process(self) -> Optional[Process]:
        if not self.ready_queue:
            return None
        available = [p for p in self.ready_queue if p.arrival_time <= self.current_time]
        if not available:
            return None
        available.sort(key=lambda p: p.priority)
        process = available[0]
        self.ready_queue.remove(process)
        return process


class RoundRobinScheduler(BaseScheduler):
    """Round Robin Scheduler"""
    
    def __init__(self, time_quantum: int = 4):
        super().__init__("Round Robin")
        self.time_quantum = time_quantum
        self.is_preemptive = True
        self.original_queue: List[Process] = []
    
    def add_process(self, process: Process):
        process.state = ProcessState.READY
        if process not in self.ready_queue:
            self.ready_queue.append(process)
        if process not in self.original_queue:
            self.original_queue.append(process)
    
    def get_next_process(self) -> Optional[Process]:
        if not self.ready_queue:
            return None
        # Find next process that has arrived
        for i, p in enumerate(self.ready_queue):
            if p.arrival_time <= self.current_time:
                return self.ready_queue.pop(i)
        return None
    
    def quantum_expired(self, process: Process):
        """Move process to end of queue if not completed"""
        if process.remaining_burst > 0:
            self.ready_queue.append(process)


class MLFQScheduler(BaseScheduler):
    """Multilevel Feedback Queue Scheduler"""
    
    def __init__(self):
        super().__init__("MLFQ")
        self.is_preemptive = True
        # Multiple queues with different priorities
        self.queues: List[List[Process]] = [
            [],  # High priority queue (RR with small quantum)
            [],  # Medium priority queue (RR with medium quantum)
            []   # Low priority queue (FCFS)
        ]
        self.quantums = [2, 4, 8]  # Different time quantums for each queue
        self.current_queue_level = 0
    
    def add_process(self, process: Process):
        process.state = ProcessState.READY
        # New processes start at highest priority queue
        if process not in self.queues[0] and process not in self.queues[1] and process not in self.queues[2]:
            self.queues[0].append(process)
    
    def get_next_process(self) -> Optional[Process]:
        # Check queues in priority order
        for i, queue in enumerate(self.queues):
            for p in queue:
                if p.arrival_time <= self.current_time:
                    queue.remove(p)
                    self.current_queue_level = i
                    return p
        return None
    
    def demote_process(self, process: Process):
        """Move process to lower priority queue"""
        for queue in self.queues:
            if process in queue:
                queue.remove(process)
                break
        
        # Add to next lower queue if not at lowest
        if self.current_queue_level < len(self.queues) - 1:
            self.queues[self.current_queue_level + 1].append(process)
        else:
            self.queues[-1].append(process)
            
    def update_process_times(self, current_process: Process, time_slice: int):
        """Update waiting times for processes in MLFQ queues"""
        for queue in self.queues:
            for p in queue:
                if p.pid != current_process.pid and p.state == ProcessState.READY:
                    p.waiting_time += time_slice
    
    def reset(self):
        super().reset()
        self.queues = [[], [], []]
        self.current_queue_level = 0



# Nice values mapping from -20 to 19 (length 40)
NICE_TO_WEIGHT = [
    88761, 71755, 56483, 46273, 36291,  # -20 to -16
    29154, 23254, 18705, 14949, 11916,  # -15 to -11
    9548,  7620,  6100,  4904,  3906,   # -10 to -6
    3121,  2501,  1991,  1586,  1277,   # -5 to -1
    1024,  820,   655,   526,   423,    # 0 to 4
    335,   272,   215,   172,   137,    # 5 to 9
    110,   87,    70,    56,    45,     # 10 to 14
    36,    29,    23,    18,    15      # 15 to 19
]


class CFSScheduler(BaseScheduler):
    """Linux completely Fair Scheduler (CFS)"""
    
    def __init__(self):
        super().__init__("CFS")
        self.is_preemptive = True

    def get_nice_weight(self, nice_val: int) -> int:
        nice_val = max(-20, min(19, nice_val))
        return NICE_TO_WEIGHT[nice_val + 20]

    def add_process(self, process: Process):
        process.state = ProcessState.READY
        # Starvation prevention: initialize vruntime to minimum vruntime in queue
        min_vruntime = 0.0
        if self.ready_queue:
            min_vruntime = min(getattr(p, 'vruntime', 0.0) for p in self.ready_queue)
        process.vruntime = max(getattr(process, 'vruntime', 0.0), min_vruntime)
        
        self.ready_queue.append(process)
        self.ready_queue.sort(key=lambda p: p.vruntime)

    def get_next_process(self) -> Optional[Process]:
        if not self.ready_queue:
            return None
        for p in self.ready_queue:
            if p.arrival_time <= self.current_time:
                self.ready_queue.remove(p)
                return p
        return None

    def update_process_times(self, current_process: Process, time_slice: int):
        super().update_process_times(current_process, time_slice)
        # Scale vruntime based on process niceness weight
        weight = self.get_nice_weight(current_process.nice)
        delta_vruntime = time_slice * (1024.0 / weight)
        current_process.vruntime += delta_vruntime


class RateMonotonicScheduler(BaseScheduler):
    """Rate Monotonic Scheduling (RMS) - Static Priority Real-time Scheduler"""
    
    def __init__(self):
        super().__init__("RMS")
        self.is_preemptive = True

    def add_process(self, process: Process):
        process.state = ProcessState.READY
        self.ready_queue.append(process)
        # Sort by period: shorter period = higher priority
        self.ready_queue.sort(key=lambda p: p.period if p.period > 0 else float('inf'))

    def get_next_process(self) -> Optional[Process]:
        if not self.ready_queue:
            return None
        for p in self.ready_queue:
            if p.arrival_time <= self.current_time:
                self.ready_queue.remove(p)
                return p
        return None


class EarliestDeadlineFirstScheduler(BaseScheduler):
    """Earliest Deadline First (EDF) - Dynamic Priority Real-time Scheduler"""
    
    def __init__(self):
        super().__init__("EDF")
        self.is_preemptive = True

    def add_process(self, process: Process):
        process.state = ProcessState.READY
        self.ready_queue.append(process)
        # Sort by absolute deadline
        self.ready_queue.sort(key=lambda p: p.deadline if p.deadline > 0 else float('inf'))

    def get_next_process(self) -> Optional[Process]:
        if not self.ready_queue:
            return None
        for p in self.ready_queue:
            if p.arrival_time <= self.current_time:
                self.ready_queue.remove(p)
                return p
        return None


class AdaptiveScheduler:
    """
    Adaptive Feedback Mechanism
    Dynamically adjusts scheduling strategy based on system behavior
    """
    
    def __init__(self):
        self.current_algorithm = SchedulingAlgorithm.FCFS
        self.load_history: List[float] = []
    
    def analyze_workload(self, processes: List[Process]) -> str:
        """Analyze workload characteristics"""
        if not processes:
            return "FCFS"
        
        cpu_bound = sum(1 for p in processes if not p.is_io_bound)
        io_bound = len(processes) - cpu_bound
        
        avg_burst = sum(p.burst_time for p in processes) / len(processes)
        
        # Determine workload type
        if io_bound > cpu_bound:
            return "RR"  # I/O bound processes benefit from Round Robin
        elif avg_burst < 5:
            return "SJF"  # Short jobs benefit from SJF
        elif any(p.priority < 3 for p in processes):
            return "PRIORITY"
        else:
            return "MLFQ"  # Mixed workload benefits from MLFQ
    
    def suggest_algorithm(self, processes: List[Process], current_metrics: Dict) -> str:
        """Suggest optimal algorithm based on current state"""
        # Analyze system load
        queue_length = len(processes)
        avg_waiting = current_metrics.get('avg_waiting_time', 0)
        
        # Decision logic
        if queue_length > 10 and avg_waiting > 20:
            return "MLFQ"  # High load - use MLFQ for better response
        elif queue_length > 5:
            return "RR"  # Medium load - use RR for fairness
        elif queue_length <= 3:
            return "SJF"  # Low load - use SJF for efficiency
        else:
            return "FCFS"  # Default
    
    def get_adaptive_feedback(self, scheduler: BaseScheduler, metrics: Dict) -> str:
        """Generate adaptive feedback message"""
        suggestions = []
        
        if metrics['avg_waiting_time'] > 15:
            suggestions.append("High waiting time detected. Consider switching to Round Robin for better fairness.")
        
        if metrics['cpu_utilization'] < 50:
            suggestions.append("Low CPU utilization. The system may be spending too much time in context switching.")
        
        if metrics['throughput'] < 0.5:
            suggestions.append("Low throughput. Consider using a shorter time quantum or different algorithm.")
        
        if not suggestions:
            suggestions.append("System performance is optimal for current workload.")
        
        return "\n".join(suggestions)


class SchedulingSimulator:
    """
    Main Scheduling Simulator Class
    Coordinates all scheduling operations and GUI updates
    """
    
    def __init__(self):
        self.processes: List[Process] = []
        self.scheduler: BaseScheduler = FCFSScheduler()
        self.adaptive_scheduler = AdaptiveScheduler()
        self.memory_manager = MemoryManager()
        self.memory_manager.simulator = self
        self.is_running = False
        self.is_paused = False
        self.current_process: Optional[Process] = None
        self.gantt_chart: List[Dict] = []  # [(start_time, end_time, process_name, color)]
        self.next_pid = 1
        self.simulation_speed = 1.0  # 1x speed
        self.time_quantum = 4
        self.callbacks: List[callable] = []
        self.memory_time_area = 0.0  # For memory utilization tracking
        # New: Detailed timeline and execution tracking
        self.timeline_log: List[Dict] = []  # Detailed timeline of all events
        self.execution_history: List[Dict] = []  # Complete execution history
    
    def add_process(self, name: str, arrival: int, burst: int, priority: int = 0, is_io: bool = False, memory_required: int = 100, nice: int = 0, deadline: int = 0, period: int = 0) -> Process:
        """Add a new process to the simulator"""
        process = Process(
            pid=self.next_pid,
            name=name,
            arrival_time=arrival,
            burst_time=burst,
            memory_required=memory_required,
            priority=priority,
            is_io_bound=is_io,
            nice=nice,
            deadline=deadline,
            period=period
        )
        self.next_pid += 1
        self.processes.append(process)
        return process
    
    def remove_process(self, pid: int):
        """Remove a process by PID"""
        self.processes = [p for p in self.processes if p.pid != pid]
    
    def set_algorithm(self, algorithm: SchedulingAlgorithm):
        """Change the scheduling algorithm"""
        old_time = self.scheduler.current_time
        
        if algorithm == SchedulingAlgorithm.FCFS:
            self.scheduler = FCFSScheduler()
        elif algorithm == SchedulingAlgorithm.SJF:
            self.scheduler = SJFScheduler(preemptive=False)
        elif algorithm == SchedulingAlgorithm.PRIORITY:
            self.scheduler = PriorityScheduler(preemptive=False)
        elif algorithm == SchedulingAlgorithm.ROUND_ROBIN:
            self.scheduler = RoundRobinScheduler(time_quantum=self.time_quantum)
        elif algorithm == SchedulingAlgorithm.MLFQ:
            self.scheduler = MLFQScheduler()
        elif algorithm == SchedulingAlgorithm.CFS:
            self.scheduler = CFSScheduler()
        elif algorithm == SchedulingAlgorithm.RMS:
            self.scheduler = RateMonotonicScheduler()
        elif algorithm == SchedulingAlgorithm.EDF:
            self.scheduler = EarliestDeadlineFirstScheduler()
        
        self.scheduler.current_time = old_time
        self.adaptive_scheduler.current_algorithm = algorithm
        
        # Re-add only READY processes to new scheduler
        for process in self.processes:
            if process.state == ProcessState.READY:
                self.scheduler.add_process(process)
    
    def _admit_new_processes(self) -> bool:
        """Admit processes that have arrived and have available memory."""
        admitted_any = False
        for process in self.processes:
            if process.state == ProcessState.NEW and process.arrival_time <= self.scheduler.current_time:
                if self.memory_manager.allocate(process):
                    process.waiting_time += (self.scheduler.current_time - process.arrival_time)
                    self.scheduler.add_process(process)
                    admitted_any = True
        return admitted_any

    def start_simulation(self):
        """Start the simulation"""
        import random
        random.seed(42)
        self.is_running = True
        self.is_paused = False
        self._admit_new_processes()
    
    def pause_simulation(self):
        """Pause the simulation"""
        self.is_paused = True
    
    def resume_simulation(self):
        """Resume the simulation"""
        self.is_paused = False
    
    def step_simulation(self) -> bool:
        """Execute one step of simulation"""
        if not self.is_running or self.is_paused:
            return False
        
        # Admit any newly arrived processes before selecting the next process
        self._admit_new_processes()
        
        # Get next process
        process = self.scheduler.get_next_process()
        
        if process is None:
            # Check if there are processes waiting for I/O
            waiting = [p for p in self.processes if p.state == ProcessState.WAITING]
            if waiting:
                min_io = min(getattr(p, 'io_completion_time', float('inf')) for p in waiting)
                if min_io != float('inf') and self.scheduler.current_time < min_io:
                    # Advance time to next I/O completion
                    idle_duration = min_io - self.scheduler.current_time
                    allocated_mem = self.memory_manager.allocated_memory
                    self.memory_time_area += allocated_mem * idle_duration
                    self.scheduler.current_time = min_io
                    
                    # Wake up ready processes
                    for p in waiting:
                        if getattr(p, 'io_completion_time', -1) <= self.scheduler.current_time:
                            p.waiting_time += (self.scheduler.current_time - getattr(p, 'io_completion_time'))
                            p.state = ProcessState.READY
                            p.state_history.append((self.scheduler.current_time, ProcessState.READY))
                            self.scheduler.add_process(p)
                    return True
            
            # Check if there are processes that haven't arrived yet
            upcoming = [p for p in self.processes if p.state == ProcessState.NEW]
            if upcoming:
                min_arrival = min(p.arrival_time for p in upcoming)
                
                # Advance time to next arrival if we are before it
                if self.scheduler.current_time < min_arrival:
                    idle_duration = min_arrival - self.scheduler.current_time
                    allocated_mem = self.memory_manager.allocated_memory
                    self.memory_time_area += allocated_mem * idle_duration
                    self.scheduler.current_time = min_arrival
                
                allocated_any = False
                for p in upcoming:
                    if p.arrival_time <= self.scheduler.current_time:
                        if self.memory_manager.allocate(p):
                            self.scheduler.add_process(p)
                            allocated_any = True
                
                if allocated_any:
                    return True
                else:
                    # Deadlock: No running processes to free memory, and NEW processes cannot be allocated
                    self.is_running = False
                    self.timeline_log.append({
                        'time': self.scheduler.current_time,
                        'event': 'DEADLOCK_DETECTED',
                        'process': 'System',
                        'pid': 0,
                        'remaining': 0
                    })
                    return False
            
            self.is_running = False
            return False
        
        # Execute process
        self.current_process = process
        process.state = ProcessState.RUNNING
        
        # Virtual Memory Page Access Check
        if self.memory_manager.paging_enabled and hasattr(process, 'page_table') and process.page_table:
            # Determine which page is accessed based on program progress
            num_pages = len(process.page_table)
            progress = (process.burst_time - process.remaining_burst) / max(1, process.burst_time)
            current_page = min(num_pages - 1, int(progress * num_pages))
            
            page_accessed = self.memory_manager.access_page(process, current_page, self.scheduler.current_time)
            if not page_accessed:
                # Trigger Page Fault Penalty
                penalty = self.memory_manager.page_fault_penalty
                
                # Record page fault event
                self.timeline_log.append({
                    'time': self.scheduler.current_time,
                    'event': 'PAGE_FAULT',
                    'process': process.name,
                    'pid': process.pid,
                    'page': current_page,
                    'penalty': penalty
                })
                
                # Add penalty segment to Gantt chart
                color = self._get_process_color(process.pid)
                self.gantt_chart.append({
                    'start': self.scheduler.current_time,
                    'end': self.scheduler.current_time + penalty,
                    'process': f"{process.name} (Fault)",
                    'pid': process.pid,
                    'color': '#ef4444'  # Vibrant Red for Page Fault
                })
                
                # Advance time by penalty
                self.scheduler.current_time += penalty
                
                # Update other process waiting times
                self.scheduler.update_process_times(process, penalty)
                
                # Wake up ready processes whose I/O finished during this penalty
                for p in self.processes:
                    if p.state == ProcessState.WAITING and getattr(p, 'io_completion_time', -1) <= self.scheduler.current_time:
                        p.waiting_time += (self.scheduler.current_time - getattr(p, 'io_completion_time'))
                        p.state = ProcessState.READY
                        p.state_history.append((self.scheduler.current_time, ProcessState.READY))
                        self.scheduler.add_process(p)
                
                # Return the process to the READY state for scheduling on the next step
                process.state = ProcessState.READY
                process.state_history.append((self.scheduler.current_time, ProcessState.READY))
                self.scheduler.add_process(process)
                
                return True

        # Track first start time and response time
        if process.first_start_time == -1:
            process.first_start_time = self.scheduler.current_time
            process.response_time = self.scheduler.current_time - process.arrival_time
        
        # Record state change
        process.state_history.append((self.scheduler.current_time, ProcessState.RUNNING))
        
        if process.start_time == -1:
            process.start_time = self.scheduler.current_time
        
        # Determine time slice
        quantum = float('inf')
        if isinstance(self.scheduler, RoundRobinScheduler):
            quantum = self.scheduler.time_quantum
        elif isinstance(self.scheduler, MLFQScheduler):
            quantum = self.scheduler.quantums[self.scheduler.current_queue_level]
        
        time_slice = min(quantum, process.remaining_burst)
        process.used_full_quantum = (time_slice == quantum)
        
        # True Preemption Check (Arrivals & I/O Completions)
        if self.scheduler.is_preemptive:
            upcoming_arrivals = [p.arrival_time for p in self.processes if p.state == ProcessState.NEW and p.arrival_time > self.scheduler.current_time]
            io_completions = [getattr(p, 'io_completion_time', -1) for p in self.processes if p.state == ProcessState.WAITING and getattr(p, 'io_completion_time', -1) > self.scheduler.current_time]
            
            upcoming_events = upcoming_arrivals + io_completions
            if upcoming_events:
                next_event = min(upcoming_events)
                if next_event < self.scheduler.current_time + time_slice:
                    time_slice = next_event - self.scheduler.current_time
                    process.used_full_quantum = False
                    
        # Yield to I/O logic determination BEFORE executing slice
        yielded_to_io = False
        io_time = 0
        if process.is_io_bound and time_slice > 0:
            if random.random() < 0.3:  # 30% chance to block for I/O
                if process.remaining_burst > 1:
                    yielded_to_io = True
                    if time_slice > 1:
                        time_slice = random.randint(1, time_slice - 1)
                    else:
                        time_slice = 1
                    io_time = random.randint(5, 15)
        
        # Track memory utilization
        allocated_mem = self.memory_manager.allocated_memory
        self.memory_time_area += allocated_mem * time_slice
        
        # Execute for time slice
        process.remaining_burst -= time_slice
        self.scheduler.current_time += time_slice
        
        # Check I/O completions that happened during this time slice
        for p in self.processes:
            if p.state == ProcessState.WAITING and getattr(p, 'io_completion_time', -1) <= self.scheduler.current_time:
                p.waiting_time += (self.scheduler.current_time - getattr(p, 'io_completion_time'))
                p.state = ProcessState.READY
                p.state_history.append((self.scheduler.current_time, ProcessState.READY))
                self.scheduler.add_process(p)
        
        # Update waiting times
        self.scheduler.update_process_times(process, time_slice)
        
        # Add to Gantt chart
        color = self._get_process_color(process.pid)
        self.gantt_chart.append({
            'start': self.scheduler.current_time - time_slice,
            'end': self.scheduler.current_time,
            'process': process.name,
            'pid': process.pid,
            'color': color
        })
        
        # Record detailed execution in timeline
        self.timeline_log.append({
            'time': self.scheduler.current_time - time_slice,
            'event': 'CPU_BURST_START',
            'process': process.name,
            'pid': process.pid,
            'duration': time_slice,
            'remaining': process.remaining_burst
        })
        
        self.timeline_log.append({
            'time': self.scheduler.current_time,
            'event': 'CPU_BURST_END',
            'process': process.name,
            'pid': process.pid,
            'remaining': process.remaining_burst
        })
        
        # Record execution history
        self.execution_history.append({
            'start': self.scheduler.current_time - time_slice,
            'end': self.scheduler.current_time,
            'process_name': process.name,
            'pid': process.pid,
            'duration': time_slice,
            'state': 'Running'
        })
        
        # Yield to I/O logic
        if yielded_to_io:
            process.state = ProcessState.WAITING
            process.io_completion_time = self.scheduler.current_time + io_time
            process.state_history.append((self.scheduler.current_time, ProcessState.WAITING))
            process.used_full_quantum = False
        
        if process.remaining_burst <= 0:
            # Process completed
            process.completion_time = self.scheduler.current_time
            process.turnaround_time = process.completion_time - process.arrival_time
            if not process.is_io_bound:
                process.waiting_time = process.turnaround_time - process.burst_time
            process.state = ProcessState.TERMINATED
            
            # Deallocate memory
            self.memory_manager.deallocate(process.pid)
            
            # Try to admit NEW processes with newly freed memory
            self._admit_new_processes()
            
            # Record termination
            process.state_history.append((self.scheduler.current_time, ProcessState.TERMINATED))
            self.timeline_log.append({
                'time': self.scheduler.current_time,
                'event': 'PROCESS_TERMINATED',
                'process': process.name,
                'pid': process.pid,
                'waiting_time': process.waiting_time,
                'turnaround_time': process.turnaround_time
            })
            
            self.scheduler.completed_processes.append(process)
        elif yielded_to_io:
            self.timeline_log.append({
                'time': self.scheduler.current_time,
                'event': 'BLOCKED_FOR_IO',
                'process': process.name,
                'pid': process.pid,
                'remaining': process.remaining_burst
            })
        else:
            # Process not completed - goes to ready queue
            process.state = ProcessState.READY
            process.state_history.append((self.scheduler.current_time, ProcessState.READY))
            
            # Record that process went back to ready queue
            self.timeline_log.append({
                'time': self.scheduler.current_time,
                'event': 'TO_READY_QUEUE',
                'process': process.name,
                'pid': process.pid,
                'remaining': process.remaining_burst
            })
            
            # For preemptive schedulers, add back to queue
            if self.scheduler.is_preemptive:
                if isinstance(self.scheduler, RoundRobinScheduler):
                    self.scheduler.ready_queue.append(process)
                elif isinstance(self.scheduler, MLFQScheduler):
                    if getattr(process, 'used_full_quantum', False):
                        self.scheduler.demote_process(process)
                    else:
                        self.scheduler.queues[self.scheduler.current_queue_level].append(process)
                elif isinstance(self.scheduler, SJFScheduler):
                    self.scheduler.ready_queue.append(process)
                    self.scheduler.ready_queue.sort(key=lambda p: p.remaining_burst)
                elif isinstance(self.scheduler, PriorityScheduler):
                    self.scheduler.ready_queue.append(process)
                    self.scheduler.ready_queue.sort(key=lambda p: p.priority)
        
        # Notify callbacks
        self._notify_callbacks()
        
        return True
    
    def _get_process_color(self, pid: int) -> str:
        """Get a unique color for each process"""
        colors = [
            '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7',
            '#DDA0DD', '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E9'
        ]
        return colors[(pid - 1) % len(colors)]
    
    def get_metrics(self) -> Dict:
        """Get current performance metrics"""
        metrics = self.scheduler.calculate_metrics()
        total_time = self.scheduler.current_time
        
        # Calculate precise CPU utilization using Gantt chart
        if total_time > 0:
            total_busy = sum(segment['end'] - segment['start'] for segment in self.gantt_chart)
            metrics['cpu_utilization'] = (total_busy / total_time) * 100
        else:
            metrics['cpu_utilization'] = 0.0
            
        if total_time > 0 and self.memory_manager.total_memory > 0:
            metrics['memory_utilization'] = (self.memory_time_area / (self.memory_manager.total_memory * total_time)) * 100
        else:
            metrics['memory_utilization'] = 0.0
        return metrics
    
    def get_adaptive_feedback(self) -> str:
        """Get adaptive feedback"""
        return self.adaptive_scheduler.get_adaptive_feedback(self.scheduler, self.get_metrics())
    
    def register_callback(self, callback: callable):
        """Register a callback for simulation updates"""
        self.callbacks.append(callback)
    
    def _notify_callbacks(self):
        """Notify all registered callbacks"""
        import traceback
        for callback in self.callbacks:
            try:
                callback()
            except Exception as e:
                print(f"Error in callback {callback}: {e}")
                traceback.print_exc()
    
    def reset(self):
        """Reset the simulation"""
        self.is_running = False
        self.is_paused = False
        self.current_process = None
        self.gantt_chart = []
        self.timeline_log = []
        self.execution_history = []
        self.memory_time_area = 0.0
        self.scheduler.reset()
        self.memory_manager.reset()
        
        # Reset all processes
        for process in self.processes:
            process.remaining_burst = process.burst_time
            process.waiting_time = 0
            process.turnaround_time = 0
            process.completion_time = 0
            process.start_time = -1
            process.first_start_time = -1
            process.response_time = -1
            process.state = ProcessState.NEW
            process.state_history = []
            process.cpu_burst_history = []
            process.execution_log = []
            if hasattr(process, 'io_completion_time'):
                del process.io_completion_time


# Premium Slate-Dark Theme Colors
COLORS = {
    'primary': '#4f46e5',       # Vibrant Indigo
    'secondary': '#06b6d4',     # Electric Cyan
    'accent': '#ef4444',        # Bright Coral Red
    'success': '#10b981',       # Emerald Green
    'warning': '#f59e0b',       # Amber Yellow
    'background': '#0f172a',    # Deep Slate Background (Slate 900)
    'surface': '#1e293b',       # Dark Slate Card/Surface (Slate 800)
    'surface_light': '#334155', # Slate Border/Separator (Slate 700)
    'text': '#f8fafc',          # Off-white / High Contrast Text (Slate 50)
    'light_text': '#94a3b8'     # Soft Slate Text (Slate 400)
}

# Premium Multi-Theme Dictionary
THEMES = {
    "Slate Dark": {
        'primary': '#4f46e5',       # Indigo
        'secondary': '#06b6d4',     # Cyan
        'accent': '#ef4444',        # Red
        'success': '#10b981',       # Emerald
        'warning': '#f59e0b',       # Amber
        'background': '#0f172a',    # Slate 900
        'surface': '#1e293b',       # Slate 800
        'surface_light': '#334155', # Slate 700
        'text': '#f8fafc',          # White
        'light_text': '#94a3b8'     # Slate 400
    },
    "Emerald Matrix": {
        'primary': '#10b981',       # Emerald Green
        'secondary': '#34d399',     # Light Emerald
        'accent': '#f43f5e',        # Rose Red
        'success': '#059669',       # Deep Green
        'warning': '#fbbf24',       # Amber Gold
        'background': '#022c22',    # Dark Forest (Green 950)
        'surface': '#064e3b',       # Forest Card (Green 900)
        'surface_light': '#0f766e', # Teal Accent
        'text': '#ecfdf5',          # Mint Text (Green 50)
        'light_text': '#6ee7b7'     # Soft Mint
    },
    "Cyberpunk Neon": {
        'primary': '#d946ef',       # Fuchsia
        'secondary': '#f43f5e',     # Synthwave Pink/Rose
        'accent': '#eab308',        # Neon Yellow
        'success': '#10b981',       # Emerald Green
        'warning': '#f97316',       # Neon Orange
        'background': '#1e1b4b',    # Dark Indigo (Indigo 950)
        'surface': '#312e81',       # Indigo Card (Indigo 900)
        'surface_light': '#4338ca', # Accent Purple
        'text': '#fdf2ff',          # Lavender White
        'light_text': '#c084fc'     # Pastel Violet
    },
    "Dracula Classic": {
        'primary': '#ff79c6',       # Dracula Pink
        'secondary': '#8be9fd',     # Dracula Cyan
        'accent': '#ff5555',        # Dracula Red
        'success': '#50fa7b',       # Dracula Green
        'warning': '#f1fa8c',       # Dracula Yellow
        'background': '#282a36',    # Dark Dracula Charcoal
        'surface': '#44475a',       # Dracula Slate Gray
        'surface_light': '#6272a4', # Dracula Purple Gray
        'text': '#f8f8f2',          # Clean White
        'light_text': '#a4b9df'     # Slate Blue Text
    },
    "Solarized Light": {
        'primary': '#268bd2',       # Solarized Blue
        'secondary': '#2aa198',     # Solarized Cyan
        'accent': '#dc322f',        # Solarized Red
        'success': '#859900',       # Solarized Green
        'warning': '#b58900',       # Solarized Yellow
        'background': '#fdf6e3',    # Warm Cream (Base 3)
        'surface': '#eee8d5',       # Light Cream Card (Base 2)
        'surface_light': '#93a1a1', # Muted Silver
        'text': '#073642',          # Deep Dark Blue-Gray (Base 02)
        'light_text': '#586e75'     # Muted solarized gray (Base 01)
    }
}


class SchedulingSimulatorGUI:
    """
    Graphical User Interface for the Scheduling Simulator
    """
    
    def __init__(self, root):
        self.root = root
        self.root.title("Interactive CPU Scheduling Simulator")
        self.root.geometry("1400x1000")
        self.root.configure(bg=COLORS['background'])
        
        self.simulator = SchedulingSimulator()
        self.simulator.register_callback(self.update_display)
        
        # Initialize all widget attributes to prevent AttributeError
        self.details_tree = None
        self.timeline_canvas = None
        self.log_text = None
        self.state_timeline_canvas = None
        self.state_details_text = None
        self.timeline_process_combo = None
        self.timeline_process_var = None
        self.notebook = None
        self.process_tree = None
        self.gantt_canvas = None
        self.metrics_text = None
        self.time_label = None
        self.memory_canvas = None
        self.memory_algorithm_var = None
        self.total_memory_var = None
        self.memory_stats_label = None
        self.benchmark_history = {}
        self.title_label = None
        self.theme_combo = None
        
        # Onboarding, state, and locking attributes
        self.onboarding_frame = None
        self.onboarding_visible = True
        self.state_indicator_var = None
        self.control_widgets = []
        
        # Load startup configurations
        self.load_config()
        
        self.setup_ui()
        
        # Apply theme colors immediately if user saved a non-default theme
        if self.theme_var.get() != "Slate Dark":
            self.change_theme()
    
    def setup_ui(self):
        """Setup the user interface"""
        # Configure Premium Slate-Dark Style
        style = ttk.Style()
        style.theme_use('clam')
        
        # Configure TFrame and TLabel
        style.configure('.', background=COLORS['background'], foreground=COLORS['text'])
        style.configure('TFrame', background=COLORS['background'])
        style.configure('TLabel', background=COLORS['background'], foreground=COLORS['text'])
        style.configure('TLabelframe', background=COLORS['background'], bordercolor=COLORS['surface_light'])
        style.configure('TLabelframe.Label', background=COLORS['background'], foreground=COLORS['secondary'], font=('Helvetica', 10, 'bold'))
        
        # Configure Buttons
        style.configure('TButton', background=COLORS['primary'], foreground='white', borderwidth=0, font=('Helvetica', 9, 'bold'))
        style.map('TButton', background=[('active', COLORS['secondary'])], foreground=[('active', 'white')])
        
        # Configure Tabs (Notebook)
        style.configure('TNotebook', background=COLORS['background'], borderwidth=0)
        style.configure('TNotebook.Tab', background=COLORS['surface'], foreground=COLORS['light_text'], font=('Helvetica', 9, 'bold'), padding=(15, 6))
        style.map('TNotebook.Tab', background=[('selected', COLORS['primary'])], foreground=[('selected', 'white')])
        
        # Configure Entry & Spinbox & Combobox
        style.configure('TEntry', fieldbackground=COLORS['surface'], foreground='white', bordercolor=COLORS['surface_light'])
        style.configure('TSpinbox', fieldbackground=COLORS['surface'], foreground='white', bordercolor=COLORS['surface_light'])
        style.configure('TCombobox', fieldbackground=COLORS['surface'], foreground='white', bordercolor=COLORS['surface_light'])
        
        # Configure Treeview (tables)
        style.configure('Treeview', background=COLORS['surface'], foreground=COLORS['text'], fieldbackground=COLORS['surface'], font=('Helvetica', 9), rowheight=24)
        style.configure('Treeview.Heading', background=COLORS['surface_light'], foreground='white', font=('Helvetica', 9, 'bold'))
        style.map('Treeview', background=[('selected', COLORS['primary'])], foreground=[('selected', 'white')])
        
        # Main container
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Header container (Title + Theme Selector)
        self.header_frame = ttk.Frame(main_frame)
        self.header_frame.pack(fill=tk.X, pady=(0, 20))
        
        # Title (Left aligned)
        self.title_label = tk.Label(
            self.header_frame,
            text="Interactive CPU Scheduling Simulator",
            font=("Helvetica", 22, "bold"),
            bg=COLORS['background'],
            fg=COLORS['secondary']
        )
        self.title_label.pack(side=tk.LEFT)
        
        # Theme selector (Right aligned)
        theme_frame = ttk.Frame(self.header_frame)
        theme_frame.pack(side=tk.RIGHT, anchor=tk.E)
        
        ttk.Label(theme_frame, text="Theme:", font=("Helvetica", 10, "bold")).pack(side=tk.LEFT, padx=5)
        self.theme_combo = ttk.Combobox(
            theme_frame,
            textvariable=self.theme_var,
            values=["Slate Dark", "Emerald Matrix", "Cyberpunk Neon", "Dracula Classic", "Solarized Light"],
            state="readonly",
            width=15
        )
        self.theme_combo.pack(side=tk.LEFT, padx=5)
        self.theme_combo.bind('<<ComboboxSelected>>', lambda e: self.change_theme())
        
        # Theme swatch canvas preview
        self.theme_swatch_canvas = tk.Canvas(
            theme_frame,
            width=35,
            height=18,
            bg=COLORS['surface'],
            highlightthickness=1,
            highlightbackground=COLORS['surface_light']
        )
        self.theme_swatch_canvas.pack(side=tk.LEFT, padx=3)
        self.draw_theme_swatch()
        
        # Reset Theme Button
        self.reset_theme_btn = ttk.Button(theme_frame, text="Reset", width=6, command=self.reset_theme_to_default)
        self.reset_theme_btn.pack(side=tk.LEFT, padx=3)
        
        # Help Button (?) next to theme
        self.help_btn = ttk.Button(theme_frame, text="?", width=3, command=self.toggle_onboarding)
        self.help_btn.pack(side=tk.LEFT, padx=5)
        
        # Onboarding / Help Guide Panel
        self.create_onboarding_panel(main_frame)
        if self.onboarding_visible:
            self.onboarding_frame.pack(fill=tk.X, pady=(0, 15))
        else:
            self.onboarding_frame.pack_forget()
        
        # Control Panel (Top)
        control_frame = self.create_control_panel(main_frame)
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Create Notebook for tabs
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Tab 1: Main Simulation View
        self.create_main_simulation_tab()
        
        # Tab 2: Scheduling Details & Timeline
        self.create_scheduling_details_tab()
        
        # Tab 3: Process State Timeline
        self.create_process_timeline_tab()
        
        # Tab 4: Memory Management
        self.create_memory_management_tab()
        
        # Tab 5: Analytics Dashboard
        self.create_analytics_tab()
    
    def create_main_simulation_tab(self):
        """Create the main simulation tab"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Simulation")
        
        # Middle Section - Process Input and Tables
        middle_frame = ttk.Frame(tab)
        middle_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Left Sidebar (Inputs + Presets)
        left_sidebar = ttk.Frame(middle_frame)
        left_sidebar.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 10))
        
        input_frame = self.create_input_panel(left_sidebar)
        input_frame.pack(fill=tk.X, pady=(0, 10))
        
        presets_frame = self.create_presets_panel(left_sidebar)
        presets_frame.pack(fill=tk.X)
        
        # Right: Process List
        process_list_frame = self.create_process_list_panel(middle_frame)
        process_list_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # Bottom Section - Visualization and Metrics
        bottom_frame = ttk.Frame(tab)
        bottom_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Left: Gantt Chart
        gantt_frame = self.create_gantt_panel(bottom_frame)
        gantt_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        # Right: Metrics and Feedback
        metrics_frame = self.create_metrics_panel(bottom_frame)
        metrics_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
    
    def create_scheduling_details_tab(self):
        """Create the scheduling details tab with timeline preview"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Scheduling Details")
        
        # Create frames for different sections
        top_frame = ttk.Frame(tab)
        top_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Left: Process Execution Details
        details_frame = ttk.LabelFrame(top_frame, text="Process Execution Details", padding=10)
        details_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        # Treeview for process details
        columns = ('PID', 'Name', 'Arrival', 'Burst', 'Start', 'End', 'Wait', 'Turnaround', 'Response', 'State')
        self.details_tree = ttk.Treeview(details_frame, columns=columns, show='headings', height=10)
        
        for col in columns:
            self.details_tree.heading(col, text=col)
            self.details_tree.column(col, width=70)
        
        self.details_tree.column('Name', width=80)
        self.details_tree.column('State', width=80)
        
        self.details_tree.pack(fill=tk.BOTH, expand=True)
        
        # Scrollbar
        details_scroll = ttk.Scrollbar(details_frame, orient=tk.VERTICAL, command=self.details_tree.yview)
        self.details_tree.configure(yscrollcommand=details_scroll.set)
        
        # Right: Timeline Preview
        timeline_frame = ttk.LabelFrame(top_frame, text="Timeline Preview", padding=10)
        timeline_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        # --- Bottom controls first so canvas fills remaining space ---
        tl_zoom_frame = ttk.Frame(timeline_frame)
        tl_zoom_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(2, 0))
        ttk.Label(tl_zoom_frame, text="Zoom:").pack(side=tk.LEFT, padx=(0, 4))
        self.timeline_zoom_var = tk.DoubleVar(value=1.0)
        tl_zoom = ttk.Scale(tl_zoom_frame, from_=0.5, to=8.0, orient=tk.HORIZONTAL,
                            variable=self.timeline_zoom_var,
                            command=lambda _: self.update_timeline_preview())
        tl_zoom.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(tl_zoom_frame, text="8x").pack(side=tk.LEFT, padx=2)
        
        # Horizontal scrollbar
        timeline_hscroll = ttk.Scrollbar(timeline_frame, orient=tk.HORIZONTAL)
        timeline_hscroll.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Colour legend (fixed, outside canvas)
        legend_frame = ttk.Frame(timeline_frame)
        legend_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 2))
        for color, label in [('#27AE60','Running'),('#3498DB','Ready'),('#F39C12','Waiting'),('#E74C3C','Terminated')]:
            c = tk.Canvas(legend_frame, width=14, height=14, bg=color, highlightthickness=1)
            c.pack(side=tk.LEFT, padx=(6, 2))
            ttk.Label(legend_frame, text=label).pack(side=tk.LEFT, padx=(0, 8))
        
        # Vertical scrollbar (right side)
        timeline_vscroll = ttk.Scrollbar(timeline_frame, orient=tk.VERTICAL)
        timeline_vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Canvas — fills all remaining space
        self.timeline_canvas = tk.Canvas(timeline_frame, bg=COLORS['surface'], highlightthickness=0,
                                         xscrollcommand=timeline_hscroll.set,
                                         yscrollcommand=timeline_vscroll.set)
        self.timeline_canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        timeline_hscroll.config(command=self.timeline_canvas.xview)
        timeline_vscroll.config(command=self.timeline_canvas.yview)
        
        # Mouse-wheel vertical scroll
        self.timeline_canvas.bind('<MouseWheel>',
            lambda e: self.timeline_canvas.yview_scroll(int(-1*(e.delta/120)), 'units'))
        self.timeline_canvas.bind('<Button-4>',
            lambda e: self.timeline_canvas.yview_scroll(-1, 'units'))
        self.timeline_canvas.bind('<Button-5>',
            lambda e: self.timeline_canvas.yview_scroll(1, 'units'))
        
        # Bottom: Execution Log
        log_frame = ttk.LabelFrame(tab, text="Execution Log", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Log text area
        self.log_text = tk.Text(log_frame, height=12, state=tk.DISABLED, bg=COLORS['surface'], fg=COLORS['text'], insertbackground=COLORS['text'], relief=tk.FLAT)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
    
    def create_process_timeline_tab(self):
        """Create the process state timeline tab"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Process Timeline")
        
        # Process selector
        selector_frame = ttk.Frame(tab)
        selector_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(selector_frame, text="Select Process:").pack(side=tk.LEFT, padx=5)
        self.timeline_process_var = tk.StringVar()
        self.timeline_process_combo = ttk.Combobox(selector_frame, textvariable=self.timeline_process_var, state='readonly', width=15)
        self.timeline_process_combo.pack(side=tk.LEFT, padx=5)
        self.timeline_process_combo.bind('<<ComboboxSelected>>', lambda e: self.update_process_timeline())
        
        ttk.Button(selector_frame, text="Refresh", command=self.update_process_timeline).pack(side=tk.LEFT, padx=5)
        
        # Process state timeline canvas
        state_timeline_frame = ttk.LabelFrame(tab, text="Process State Timeline", padding=10)
        state_timeline_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Process state timeline canvas with horizontal scrollbar (pack bottom items first)
        st_zoom_frame = ttk.Frame(state_timeline_frame)
        st_zoom_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(2, 0))
        ttk.Label(st_zoom_frame, text="Zoom:").pack(side=tk.LEFT, padx=(0, 4))
        self.state_zoom_var = tk.DoubleVar(value=1.0)
        st_zoom = ttk.Scale(st_zoom_frame, from_=0.5, to=8.0, orient=tk.HORIZONTAL,
                            variable=self.state_zoom_var,
                            command=lambda _: self.update_process_timeline())
        st_zoom.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(st_zoom_frame, text="0.5x").pack(side=tk.LEFT, padx=2)
        
        state_hscroll = ttk.Scrollbar(state_timeline_frame, orient=tk.HORIZONTAL)
        state_hscroll.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.state_timeline_canvas = tk.Canvas(state_timeline_frame, bg=COLORS['surface'], height=200,
                                               highlightthickness=0, xscrollcommand=state_hscroll.set)
        self.state_timeline_canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        state_hscroll.config(command=self.state_timeline_canvas.xview)
        
        # State details
        state_details_frame = ttk.LabelFrame(tab, text="State Transitions", padding=10)
        state_details_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.state_details_text = tk.Text(state_details_frame, height=10, state=tk.DISABLED, bg=COLORS['surface'], fg=COLORS['text'], insertbackground=COLORS['text'], relief=tk.FLAT)
        self.state_details_text.pack(fill=tk.BOTH, expand=True)
        
        state_scroll = ttk.Scrollbar(state_details_frame, orient=tk.VERTICAL, command=self.state_details_text.yview)
        self.state_details_text.configure(yscrollcommand=state_scroll.set)
    
    def create_memory_management_tab(self):
        """Create the memory management tab"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Memory Management")
        
        # Description
        desc = ttk.Label(tab,
            text="Live view of RAM allocation. Each coloured block = a process occupying memory. "
                 "Grey = Free. Set total RAM and allocation algorithm, then run the simulation.",
            wraplength=900, justify=tk.LEFT)
        desc.pack(fill=tk.X, padx=10, pady=(5, 0))
        
        # Controls Frame
        controls_frame = ttk.LabelFrame(tab, text="Memory Controls", padding=10)
        controls_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(controls_frame, text="Total Memory (MB):").pack(side=tk.LEFT, padx=5)
        self.total_memory_var = tk.IntVar(value=1024)
        mem_spin = ttk.Spinbox(controls_frame, from_=100, to=10000, textvariable=self.total_memory_var, width=10)
        mem_spin.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(controls_frame, text="Apply", command=self.update_total_memory).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(controls_frame, text="  Allocation Algorithm:").pack(side=tk.LEFT, padx=(20, 5))
        self.memory_algorithm_var = tk.StringVar(value="First Fit")
        algo_combo = ttk.Combobox(
            controls_frame,
            textvariable=self.memory_algorithm_var,
            values=["First Fit", "Best Fit", "Worst Fit"],
            state="readonly",
            width=15
        )
        algo_combo.pack(side=tk.LEFT, padx=5)
        algo_combo.bind('<<ComboboxSelected>>', lambda e: self.update_memory_algorithm())
        
        self.paging_enabled_var = tk.BooleanVar(value=False)
        paging_chk = ttk.Checkbutton(
            controls_frame, 
            text="Enable Virtual Memory Paging", 
            variable=self.paging_enabled_var,
            command=self.toggle_paging
        )
        paging_chk.pack(side=tk.LEFT, padx=(20, 5))
        
        # Split into top (map) and bottom (table)
        paned = ttk.PanedWindow(tab, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Memory Map canvas
        viz_frame = ttk.LabelFrame(paned, text="Memory Map  (live)", padding=10)
        paned.add(viz_frame, weight=2)
        
        self.memory_canvas = tk.Canvas(viz_frame, bg=COLORS['surface'], height=130, highlightthickness=0)
        self.memory_canvas.pack(fill=tk.BOTH, expand=True)
        
        # Swatch Legend Frame
        legend_frame = ttk.Frame(viz_frame)
        legend_frame.pack(fill=tk.X, pady=(2, 5))
        
        # Legend Items
        ttk.Label(legend_frame, text="Legend: ", font=("Helvetica", 9, "bold")).pack(side=tk.LEFT, padx=5)
        
        # Allocated RAM Swatch
        alloc_swatch = tk.Canvas(legend_frame, width=12, height=12, bg=COLORS['primary'], highlightthickness=1, highlightbackground=COLORS['surface_light'])
        alloc_swatch.pack(side=tk.LEFT, padx=(5, 2))
        ttk.Label(legend_frame, text="Active RAM Block", font=("Helvetica", 8)).pack(side=tk.LEFT, padx=(0, 10))
        
        # Swapped Disk Swatch
        swap_swatch = tk.Canvas(legend_frame, width=12, height=12, bg="#422020" if COLORS['background'] != '#fdf6e3' else '#ffdede', highlightthickness=1, highlightbackground=COLORS['surface_light'])
        swap_swatch.pack(side=tk.LEFT, padx=(5, 2))
        ttk.Label(legend_frame, text="Disk Swap Page", font=("Helvetica", 8)).pack(side=tk.LEFT, padx=(0, 10))
        
        # Free Space Swatch
        free_swatch = tk.Canvas(legend_frame, width=12, height=12, bg=COLORS['background'], highlightthickness=1, highlightbackground=COLORS['surface_light'])
        free_swatch.pack(side=tk.LEFT, padx=(5, 2))
        ttk.Label(legend_frame, text="Free Space", font=("Helvetica", 8)).pack(side=tk.LEFT, padx=(0, 10))
        
        self.memory_stats_label = ttk.Label(viz_frame, text="Total: – | Allocated: – | Free: – | Fragmentation: –", font=("Helvetica", 9, "bold"))
        self.memory_stats_label.pack(pady=3)
        
        # Allocation Table + Live Admissions Log side-by-side
        table_frame = ttk.LabelFrame(paned, text="Memory Registry & Swapping Log", padding=10)
        paned.add(table_frame, weight=1)
        
        table_container = ttk.Frame(table_frame)
        table_container.pack(fill=tk.BOTH, expand=True)
        
        # Left side: tree view table
        tree_subframe = ttk.Frame(table_container)
        tree_subframe.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        cols = ('Block #', 'Start Addr', 'Size (MB)', 'Process', 'Status')
        self.mem_table = ttk.Treeview(tree_subframe, columns=cols, show='headings', height=6)
        for c in cols:
            self.mem_table.heading(c, text=c)
            self.mem_table.column(c, width=90, anchor=tk.CENTER)
            
        mem_vsb = ttk.Scrollbar(tree_subframe, orient=tk.VERTICAL, command=self.mem_table.yview)
        self.mem_table.configure(yscrollcommand=mem_vsb.set)
        mem_vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.mem_table.pack(fill=tk.BOTH, expand=True)
        
        # Right side: Swapping & Admission Event Log listbox
        log_subframe = ttk.LabelFrame(table_container, text="Swapping & Admission Events", padding=5)
        log_subframe.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        self.mem_event_listbox = tk.Listbox(
            log_subframe,
            height=6,
            bg=COLORS['surface'],
            fg=COLORS['text'],
            relief=tk.FLAT,
            highlightthickness=0,
            font=("Helvetica", 9)
        )
        self.mem_event_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        event_scroll = ttk.Scrollbar(log_subframe, orient=tk.VERTICAL, command=self.mem_event_listbox.yview)
        self.mem_event_listbox.configure(yscrollcommand=event_scroll.set)
        event_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
    def update_total_memory(self):
        self.simulator.memory_manager.reset(self.total_memory_var.get())
        self.update_display()
        
    def update_memory_algorithm(self):
        algo_map = {
            "First Fit": MemoryAllocationAlgorithm.FIRST_FIT,
            "Best Fit": MemoryAllocationAlgorithm.BEST_FIT,
            "Worst Fit": MemoryAllocationAlgorithm.WORST_FIT
        }
        self.simulator.memory_manager.algorithm = algo_map[self.memory_algorithm_var.get()]
        self.update_display()

    def toggle_paging(self):
        """Toggle virtual memory paging on or off"""
        self.simulator.memory_manager.paging_enabled = self.paging_enabled_var.get()
        self.update_memory_visualization()

    def create_control_panel(self, parent):
        """Create the control panel"""
        frame = ttk.LabelFrame(parent, text="Control Panel", padding=10)
        
        # Reset control widgets list
        self.control_widgets = []
        
        # Algorithm Selection
        ttk.Label(frame, text="Algorithm:").grid(row=0, column=0, sticky=tk.W, padx=5)
        self.algorithm_var = tk.StringVar(value="FCFS")
        algorithm_combo = ttk.Combobox(
            frame,
            textvariable=self.algorithm_var,
            values=["FCFS", "SJF", "Priority", "Round Robin", "MLFQ", "CFS", "RMS", "EDF"],
            state="readonly",
            width=20
        )
        algorithm_combo.grid(row=0, column=1, padx=5, pady=5)
        algorithm_combo.bind('<<ComboboxSelected>>', lambda e: self.change_algorithm())
        self.control_widgets.append(algorithm_combo)
        
        # Time Quantum
        ttk.Label(frame, text="Time Quantum:").grid(row=0, column=2, sticky=tk.W, padx=5)
        self.quantum_var = tk.IntVar(value=4)
        quantum_spin = ttk.Spinbox(
            frame,
            from_=1,
            to=20,
            textvariable=self.quantum_var,
            width=5
        )
        quantum_spin.grid(row=0, column=3, padx=5, pady=5)
        quantum_spin.bind('<<Increment>>', lambda e: self.update_quantum())
        quantum_spin.bind('<<Decrement>>', lambda e: self.update_quantum())
        self.control_widgets.append(quantum_spin)
        
        # Speed Control
        ttk.Label(frame, text="Speed:").grid(row=0, column=4, sticky=tk.W, padx=5)
        self.speed_var = tk.DoubleVar(value=1.0)
        speed_combo = ttk.Combobox(
            frame,
            textvariable=self.speed_var,
            values=[0.5, 1.0, 2.0, 5.0],
            state="readonly",
            width=10
        )
        speed_combo.grid(row=0, column=5, padx=5, pady=5)
        self.control_widgets.append(speed_combo)
        
        # Control Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=0, column=6, columnspan=4, padx=20)
        
        self.start_btn = ttk.Button(btn_frame, text="Start", command=self.start_simulation)
        self.start_btn.pack(side=tk.LEFT, padx=2)
        
        self.pause_btn = ttk.Button(btn_frame, text="Pause", command=self.pause_simulation, state=tk.DISABLED)
        self.pause_btn.pack(side=tk.LEFT, padx=2)
        
        self.resume_btn = ttk.Button(btn_frame, text="Resume", command=self.resume_simulation, state=tk.DISABLED)
        self.resume_btn.pack(side=tk.LEFT, padx=2)
        
        self.step_btn = ttk.Button(btn_frame, text="Step", command=self.step_simulation)
        self.step_btn.pack(side=tk.LEFT, padx=2)
        self.control_widgets.append(self.step_btn)
        
        self.reset_btn = ttk.Button(btn_frame, text="Reset", command=self.reset_simulation)
        self.reset_btn.pack(side=tk.LEFT, padx=2)
        
        # Adaptive Button
        self.adaptive_btn = ttk.Button(frame, text="Get Adaptive Feedback", command=self.show_adaptive_feedback)
        self.adaptive_btn.grid(row=0, column=10, padx=5)
        self.control_widgets.append(self.adaptive_btn)
        
        # Dynamic Simulation State Indicator
        ttk.Label(frame, text="State:", font=("Helvetica", 9, "bold")).grid(row=0, column=11, padx=(15, 5))
        self.state_indicator_var = tk.StringVar(value="Ready")
        self.state_label = tk.Label(
            frame,
            textvariable=self.state_indicator_var,
            font=("Helvetica", 9, "bold"),
            bg=COLORS['surface'],
            fg=COLORS['success'],
            padx=8,
            pady=3,
            relief=tk.RIDGE,
            borderwidth=1
        )
        self.state_label.grid(row=0, column=12, padx=5)
        
        return frame
    
    def create_input_panel(self, parent):
        """Create the process input panel"""
        frame = ttk.LabelFrame(parent, text="Add Process", padding=10)
        
        # Process Name
        ttk.Label(frame, text="Process Name:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.name_var = tk.StringVar(value="P")
        name_entry = ttk.Entry(frame, textvariable=self.name_var, width=15)
        name_entry.grid(row=0, column=1, pady=5, padx=5)
        self.control_widgets.append(name_entry)
        
        # Arrival Time
        ttk.Label(frame, text="Arrival Time:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.arrival_var = tk.IntVar(value=0)
        arrival_spin = ttk.Spinbox(frame, from_=0, to=100, textvariable=self.arrival_var, width=13)
        arrival_spin.grid(row=1, column=1, pady=5, padx=5)
        self.control_widgets.append(arrival_spin)
        
        # Burst Time
        ttk.Label(frame, text="Burst Time:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.burst_var = tk.IntVar(value=5)
        burst_spin = ttk.Spinbox(frame, from_=1, to=100, textvariable=self.burst_var, width=13)
        burst_spin.grid(row=2, column=1, pady=5, padx=5)
        self.control_widgets.append(burst_spin)
        
        # Priority
        ttk.Label(frame, text="Priority (lower = higher):").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.priority_var = tk.IntVar(value=5)
        priority_spin = ttk.Spinbox(frame, from_=1, to=10, textvariable=self.priority_var, width=13)
        priority_spin.grid(row=3, column=1, pady=5, padx=5)
        self.control_widgets.append(priority_spin)
        
        # Memory Required
        ttk.Label(frame, text="Memory:").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.memory_var = tk.IntVar(value=100)
        memory_spin = ttk.Spinbox(frame, from_=1, to=1024, textvariable=self.memory_var, width=13)
        memory_spin.grid(row=4, column=1, pady=5, padx=5)
        self.control_widgets.append(memory_spin)
        
        # Nice Value (CFS)
        ttk.Label(frame, text="Nice Value (-20 to 19):").grid(row=5, column=0, sticky=tk.W, pady=5)
        self.nice_var = tk.IntVar(value=0)
        nice_spin = ttk.Spinbox(frame, from_=-20, to=19, textvariable=self.nice_var, width=13)
        nice_spin.grid(row=5, column=1, pady=5, padx=5)
        self.control_widgets.append(nice_spin)
        
        # Period (RMS)
        ttk.Label(frame, text="Period (RMS Task):").grid(row=6, column=0, sticky=tk.W, pady=5)
        self.period_var = tk.IntVar(value=0)
        period_spin = ttk.Spinbox(frame, from_=0, to=100, textvariable=self.period_var, width=13)
        period_spin.grid(row=6, column=1, pady=5, padx=5)
        self.control_widgets.append(period_spin)
        
        # Deadline (EDF)
        ttk.Label(frame, text="Deadline (EDF Task):").grid(row=7, column=0, sticky=tk.W, pady=5)
        self.deadline_var = tk.IntVar(value=0)
        deadline_spin = ttk.Spinbox(frame, from_=0, to=100, textvariable=self.deadline_var, width=13)
        deadline_spin.grid(row=7, column=1, pady=5, padx=5)
        self.control_widgets.append(deadline_spin)
        
        # I/O Bound
        self.io_var = tk.BooleanVar(value=False)
        io_check = ttk.Checkbutton(frame, text="I/O Bound Process", variable=self.io_var)
        io_check.grid(row=8, column=0, columnspan=2, pady=5)
        self.control_widgets.append(io_check)
        
        # Add Button
        add_btn = ttk.Button(frame, text="Add Process", command=self.add_process)
        add_btn.grid(row=9, column=0, columnspan=2, pady=10)
        self.control_widgets.append(add_btn)
        
        # Quick Add Buttons
        ttk.Label(frame, text="Quick Add:").grid(row=10, column=0, sticky=tk.W, pady=5)
        
        quick_frame = ttk.Frame(frame)
        quick_frame.grid(row=11, column=0, columnspan=2)
        
        cpu_bound_btn = ttk.Button(quick_frame, text="CPU Bound", command=self.add_sample_cpu)
        cpu_bound_btn.pack(side=tk.LEFT, padx=2)
        self.control_widgets.append(cpu_bound_btn)
        
        io_bound_btn = ttk.Button(quick_frame, text="I/O Bound", command=self.add_sample_io)
        io_bound_btn.pack(side=tk.LEFT, padx=2)
        self.control_widgets.append(io_bound_btn)
        
        random_btn = ttk.Button(quick_frame, text="Random", command=self.add_sample_random)
        random_btn.pack(side=tk.LEFT, padx=2)
        self.control_widgets.append(random_btn)
        
        return frame
    
    def create_process_list_panel(self, parent):
        """Create the process list panel"""
        frame = ttk.LabelFrame(parent, text="Process List", padding=10)
        
        # Treeview
        columns = ('PID', 'Name', 'Arrival', 'Burst', 'Memory', 'Priority', 'State', 'Remaining')
        self.process_tree = ttk.Treeview(frame, columns=columns, show='headings', height=15)
        
        for col in columns:
            self.process_tree.heading(col, text=col)
            self.process_tree.column(col, width=80)
        
        self.process_tree.column('Name', width=100)
        self.process_tree.column('State', width=80)
        
        self.process_tree.pack(fill=tk.BOTH, expand=True)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.process_tree.yview)
        self.process_tree.configure(yscrollcommand=scrollbar.set)
        
        # Delete Button
        ttk.Button(frame, text="Delete Selected", command=self.delete_process).pack(pady=5)
        
        return frame
    
    def create_gantt_panel(self, parent):
        """Create the Gantt chart panel with horizontal scrollbar and zoom"""
        frame = ttk.LabelFrame(parent, text="Gantt Chart", padding=5)
        
        # --- pack bottom-anchored items FIRST so canvas expands into remaining space ---
        
        # Time display (very bottom)
        self.time_label = ttk.Label(frame, text="Current Time: 0")
        self.time_label.pack(side=tk.BOTTOM, pady=(0, 2))
        
        # Zoom slider (above time label)
        zoom_frame = ttk.Frame(frame)
        zoom_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(2, 0))
        ttk.Label(zoom_frame, text="Zoom:").pack(side=tk.LEFT, padx=(0, 4))
        self.gantt_zoom_var = tk.DoubleVar(value=1.0)
        gantt_zoom = ttk.Scale(zoom_frame, from_=0.5, to=8.0, orient=tk.HORIZONTAL,
                               variable=self.gantt_zoom_var,
                               command=lambda _: self.update_gantt_chart())
        gantt_zoom.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(zoom_frame, text="0.5x").pack(side=tk.LEFT, padx=2)
        
        # Horizontal scrollbar (above zoom)
        gantt_hscroll = ttk.Scrollbar(frame, orient=tk.HORIZONTAL)
        gantt_hscroll.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Canvas fills all remaining space
        self.gantt_canvas = tk.Canvas(frame, bg=COLORS['surface'], height=180,
                                      highlightthickness=0, xscrollcommand=gantt_hscroll.set)
        self.gantt_canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        gantt_hscroll.config(command=self.gantt_canvas.xview)
        
        return frame
    
    def create_metrics_panel(self, parent):
        """Create the metrics panel"""
        frame = ttk.LabelFrame(parent, text="Performance Dashboard", padding=10)
        
        # Grid of Summary Cards
        cards_frame = ttk.Frame(frame)
        cards_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 4 cards in a 2x2 grid
        # Average Wait Time
        wait_card = ttk.Frame(cards_frame, relief=tk.RIDGE, borderwidth=1)
        wait_card.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        ttk.Label(wait_card, text="Avg Wait Time", font=("Helvetica", 8, "bold"), foreground=COLORS.get('text_muted', '#94a3b8')).pack(anchor=tk.W, padx=5, pady=(5, 0))
        self.avg_wait_label = ttk.Label(wait_card, text="0.00", font=("Helvetica", 12, "bold"), foreground=COLORS['secondary'])
        self.avg_wait_label.pack(anchor=tk.W, padx=5, pady=(0, 5))
        
        # Average Turnaround Time
        ta_card = ttk.Frame(cards_frame, relief=tk.RIDGE, borderwidth=1)
        ta_card.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")
        ttk.Label(ta_card, text="Avg Turnaround", font=("Helvetica", 8, "bold"), foreground=COLORS.get('text_muted', '#94a3b8')).pack(anchor=tk.W, padx=5, pady=(5, 0))
        self.avg_ta_label = ttk.Label(ta_card, text="0.00", font=("Helvetica", 12, "bold"), foreground=COLORS['secondary'])
        self.avg_ta_label.pack(anchor=tk.W, padx=5, pady=(0, 5))
        
        # CPU Utilization
        cpu_card = ttk.Frame(cards_frame, relief=tk.RIDGE, borderwidth=1)
        cpu_card.grid(row=1, column=0, padx=5, pady=5, sticky="nsew")
        ttk.Label(cpu_card, text="CPU Util", font=("Helvetica", 8, "bold"), foreground=COLORS.get('text_muted', '#94a3b8')).pack(anchor=tk.W, padx=5, pady=(5, 0))
        self.cpu_util_label = ttk.Label(cpu_card, text="0.00%", font=("Helvetica", 12, "bold"), foreground=COLORS['success'])
        self.cpu_util_label.pack(anchor=tk.W, padx=5, pady=(0, 5))
        
        # Memory Utilization
        mem_card = ttk.Frame(cards_frame, relief=tk.RIDGE, borderwidth=1)
        mem_card.grid(row=1, column=1, padx=5, pady=5, sticky="nsew")
        ttk.Label(mem_card, text="Mem Util", font=("Helvetica", 8, "bold"), foreground=COLORS.get('text_muted', '#94a3b8')).pack(anchor=tk.W, padx=5, pady=(5, 0))
        self.mem_util_label = ttk.Label(mem_card, text="0.00%", font=("Helvetica", 12, "bold"), foreground=COLORS['primary'])
        self.mem_util_label.pack(anchor=tk.W, padx=5, pady=(0, 5))
        
        cards_frame.columnconfigure(0, weight=1)
        cards_frame.columnconfigure(1, weight=1)
        
        # Scrollable log area for processes completion order
        log_label = ttk.Label(frame, text="Process Execution Summary:", font=("Helvetica", 9, "bold"))
        log_label.pack(anchor=tk.W, pady=(5, 2))
        
        self.metrics_text = tk.Text(frame, height=8, width=40, state=tk.DISABLED, bg=COLORS['surface'], fg=COLORS['text'], insertbackground=COLORS['text'], relief=tk.FLAT)
        self.metrics_text.pack(fill=tk.BOTH, expand=True)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.metrics_text.yview)
        self.metrics_text.configure(yscrollcommand=scrollbar.set)
        
        # Action Buttons frame
        actions_frame = ttk.Frame(frame)
        actions_frame.pack(fill=tk.X, pady=(10, 0))
        
        exp_btn = ttk.Button(actions_frame, text="Export Metrics", command=self.export_metrics_data)
        exp_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        
        rep_btn = ttk.Button(actions_frame, text="View Report", command=self.view_report_popup)
        rep_btn.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=2)
        
        return frame
    
    def add_process(self):
        """Add a new process"""
        name = self.name_var.get() or f"P{self.simulator.next_pid}"
        arrival = self.arrival_var.get()
        burst = self.burst_var.get()
        priority = self.priority_var.get()
        memory = self.memory_var.get()
        is_io = self.io_var.get()
        nice = self.nice_var.get()
        period = self.period_var.get()
        deadline = self.deadline_var.get()
        
        process = self.simulator.add_process(name, arrival, burst, priority, is_io, memory, nice, deadline, period)
        if process.arrival_time <= self.simulator.scheduler.current_time and process.state == ProcessState.NEW:
            if self.simulator.memory_manager.allocate(process):
                self.simulator.scheduler.add_process(process)
        
        self.update_process_table()
        self.name_var.set(f"P{self.simulator.next_pid}")
        self.nice_var.set(0)
        self.period_var.set(0)
        self.deadline_var.set(0)
    
    def add_sample_cpu(self):
        """Add a sample CPU-bound process"""
        name = f"P{self.simulator.next_pid}"
        arrival = random.randint(0, 5)
        burst = random.randint(3, 15)
        priority = random.randint(1, 10)
        memory = random.randint(50, 200)
        
        process = self.simulator.add_process(name, arrival, burst, priority, False, memory)
        if process.arrival_time <= self.simulator.scheduler.current_time and process.state == ProcessState.NEW:
            if self.simulator.memory_manager.allocate(process):
                self.simulator.scheduler.add_process(process)
        self.update_process_table()
    
    def add_sample_io(self):
        """Add a sample I/O-bound process"""
        name = f"P{self.simulator.next_pid}"
        arrival = random.randint(0, 5)
        burst = random.randint(2, 8)
        priority = random.randint(1, 10)
        memory = random.randint(50, 200)
        
        process = self.simulator.add_process(name, arrival, burst, priority, True, memory)
        if process.arrival_time <= self.simulator.scheduler.current_time and process.state == ProcessState.NEW:
            if self.simulator.memory_manager.allocate(process):
                self.simulator.scheduler.add_process(process)
        self.update_process_table()
    
    def add_sample_random(self):
        """Add a random process"""
        name = f"P{self.simulator.next_pid}"
        arrival = random.randint(0, 10)
        burst = random.randint(1, 20)
        priority = random.randint(1, 10)
        memory = random.randint(50, 200)
        is_io = random.choice([True, False])
        
        process = self.simulator.add_process(name, arrival, burst, priority, is_io, memory)
        if process.arrival_time <= self.simulator.scheduler.current_time and process.state == ProcessState.NEW:
            if self.simulator.memory_manager.allocate(process):
                self.simulator.scheduler.add_process(process)
        self.update_process_table()
    
    def delete_process(self):
        """Delete selected process"""
        selected = self.process_tree.selection()
        if selected:
            item = self.process_tree.item(selected)
            pid = int(item['values'][0])
            self.simulator.remove_process(pid)
            self.update_process_table()
    
    def change_algorithm(self):
        """Change the scheduling algorithm"""
        algo_map = {
            'FCFS': SchedulingAlgorithm.FCFS,
            'SJF': SchedulingAlgorithm.SJF,
            'Priority': SchedulingAlgorithm.PRIORITY,
            'Round Robin': SchedulingAlgorithm.ROUND_ROBIN,
            'MLFQ': SchedulingAlgorithm.MLFQ,
            'CFS': SchedulingAlgorithm.CFS,
            'RMS': SchedulingAlgorithm.RMS,
            'EDF': SchedulingAlgorithm.EDF
        }
        
        algorithm = algo_map.get(self.algorithm_var.get())
        if algorithm:
            self.simulator.set_algorithm(algorithm)
    
    def update_quantum(self):
        """Update time quantum for Round Robin"""
        self.simulator.time_quantum = self.quantum_var.get()
        if isinstance(self.simulator.scheduler, RoundRobinScheduler):
            self.simulator.scheduler.time_quantum = self.quantum_var.get()
    
    def start_simulation(self):
        """Start the simulation"""
        self.simulator.start_simulation()
        self.start_btn.config(state=tk.DISABLED)
        self.pause_btn.config(state=tk.NORMAL)
        self.resume_btn.config(state=tk.DISABLED)
        
        # Start simulation loop
        self.run_simulation()
    
    def pause_simulation(self):
        """Pause the simulation"""
        self.simulator.pause_simulation()
        self.pause_btn.config(state=tk.DISABLED)
        self.resume_btn.config(state=tk.NORMAL)
    
    def resume_simulation(self):
        """Resume the simulation"""
        self.simulator.resume_simulation()
        self.resume_btn.config(state=tk.DISABLED)
        self.pause_btn.config(state=tk.NORMAL)
        
        # Continue simulation
        self.run_simulation()
    
    def step_simulation(self):
        """Execute one step"""
        self.simulator.step_simulation()
    
    def run_simulation(self):
        """Run the simulation continuously"""
        if self.simulator.is_running and not self.simulator.is_paused:
            if self.simulator.step_simulation():
                speed = self.speed_var.get() * 1000  # Convert to milliseconds
                self.root.after(int(1000 / speed), self.run_simulation)
            else:
                # Simulation complete
                self.start_btn.config(state=tk.NORMAL)
                self.pause_btn.config(state=tk.DISABLED)
                
                # Record to benchmark history and refresh charts!
                alg_name = self.simulator.scheduler.name
                metrics = self.simulator.get_metrics()
                page_faults = self.simulator.memory_manager.total_page_faults
                self.benchmark_history[alg_name] = {
                    'avg_waiting_time': metrics['avg_waiting_time'],
                    'avg_turnaround_time': metrics['avg_turnaround_time'],
                    'throughput': metrics['throughput'],
                    'page_faults': page_faults
                }
                self.update_analytics_charts()
                
                messagebox.showinfo("Simulation Complete", "All processes have been scheduled!")
    
    def reset_simulation(self):
        """Reset the simulation"""
        self.simulator.reset()
        self.start_btn.config(state=tk.NORMAL)
        self.pause_btn.config(state=tk.DISABLED)
        self.resume_btn.config(state=tk.DISABLED)
        self.update_display()
    
    def show_adaptive_feedback(self):
        """Show adaptive feedback"""
        feedback = self.simulator.get_adaptive_feedback()
        messagebox.showinfo("Adaptive Feedback", feedback)
    
    def update_display(self):
        """Update all display elements"""
        import traceback
        try:
            self.update_simulation_state()
            self.update_process_table()
            self.update_gantt_chart()
            self.update_metrics()
            self.update_memory_visualization()
        except Exception as e:
            if "invalid command name" not in str(e) and "destroyed" not in str(e):
                print(f"Error updating main display elements: {e}")
                traceback.print_exc()
        try:
            if self.details_tree:
                self.update_scheduling_details()
                self.update_timeline_preview()
        except Exception as e:
            if "invalid command name" not in str(e) and "destroyed" not in str(e):
                print(f"Error updating scheduling details: {e}")
                traceback.print_exc()
        try:
            if self.timeline_process_combo:
                self.update_process_combo()
        except Exception as e:
            if "invalid command name" not in str(e) and "destroyed" not in str(e):
                print(f"Error updating process combo: {e}")
                traceback.print_exc()
    
    def update_scheduling_details(self):
        """Update the scheduling details tab"""
        if not self.details_tree:
            return
        
        # Clear existing items
        for item in self.details_tree.get_children():
            self.details_tree.delete(item)
        
        # Add processes with detailed info
        for process in self.simulator.processes:
            start = process.start_time if process.start_time != -1 else 0
            end = process.completion_time if process.completion_time > 0 else process.start_time
            response = process.response_time if process.response_time != -1 else 0
            
            self.details_tree.insert('', tk.END, values=(
                process.pid,
                process.name,
                process.arrival_time,
                process.burst_time,
                start,
                end,
                process.waiting_time,
                process.turnaround_time,
                response,
                process.state.value
            ))
    
    def update_timeline_preview(self):
        """Update the timeline preview canvas with scrollable rows per process"""
        if not self.timeline_canvas:
            return
        
        self.timeline_canvas.delete('all')
        
        if not self.simulator.execution_history:
            return
        
        try:
            self.timeline_canvas.update_idletasks()
        except:
            pass
        
        view_width = self.timeline_canvas.winfo_width()
        if view_width <= 1:
            view_width = 600
        
        # Apply horizontal zoom
        zoom = getattr(self, 'timeline_zoom_var', None)
        zoom = zoom.get() if zoom else 1.0
        canvas_width = max(view_width, int(view_width * zoom))
        
        # Layout constants
        LEFT_MARGIN  = 60   # space for process labels
        bar_height   = 22
        row_height   = 34
        y_start      = 10
        
        # Calculate time scale
        max_time = max((e['end'] for e in self.simulator.execution_history), default=100)
        if max_time == 0:
            max_time = 100
        
        # Group execution by process (preserve insertion order = arrival order)
        process_bars = {}
        for entry in self.simulator.execution_history:
            pid = entry['pid']
            if pid not in process_bars:
                process_bars[pid] = []
            process_bars[pid].append(entry)
        
        n_rows = len(process_bars)
        total_height = y_start + n_rows * row_height + 30  # +30 for time axis
        
        # Update scrollregion to full virtual size
        self.timeline_canvas.configure(
            scrollregion=(0, 0, canvas_width, total_height))
        
        # ---- Draw rows ----
        y_offset = y_start
        for pid, bars in process_bars.items():
            process = next((p for p in self.simulator.processes if p.pid == pid), None)
            if not process:
                y_offset += row_height
                continue
            
            proc_color = self.simulator._get_process_color(pid)
            row_mid_y  = y_offset + bar_height / 2
            
            # Alternating row background
            row_idx = list(process_bars.keys()).index(pid)
            if row_idx % 2 == 0:
                self.timeline_canvas.create_rectangle(
                    0, y_offset - 4, canvas_width, y_offset + bar_height + 4,
                    fill='#F8F9FA', outline='')
            
            # Horizontal guide line
            self.timeline_canvas.create_line(
                LEFT_MARGIN, row_mid_y, canvas_width, row_mid_y,
                fill='#DDE', dash=(2, 4))
            
            # Process name (fixed left margin — always visible when scrolling horizontally)
            self.timeline_canvas.create_text(
                2, row_mid_y,
                text=process.name, anchor=tk.W,
                font=('Arial', 8, 'bold'), fill='#2C3E50')
            
            # Execution bars
            for bar in bars:
                x1 = LEFT_MARGIN + (bar['start'] / max_time) * (canvas_width - LEFT_MARGIN - 5)
                x2 = LEFT_MARGIN + (bar['end']   / max_time) * (canvas_width - LEFT_MARGIN - 5)
                bw = x2 - x1
                
                if bw > 0:
                    self.timeline_canvas.create_rectangle(
                        x1, y_offset, x2, y_offset + bar_height,
                        fill=proc_color, outline='white', width=1)
                    if bw > 18:
                        self.timeline_canvas.create_text(
                            x1 + bw / 2, row_mid_y,
                            text=f"{bar['start']}-{bar['end']}",
                            fill='white', font=('Arial', 7))
            
            y_offset += row_height
        
        # ---- Time axis at bottom of all rows ----
        axis_y = y_offset + 4
        self.timeline_canvas.create_line(
            LEFT_MARGIN, axis_y, canvas_width - 5, axis_y,
            arrow=tk.LAST, fill='#333')
        
        step = max(1, int(max_time / max(8, int(canvas_width / 60))))
        for i in range(0, int(max_time) + 1, step):
            x = LEFT_MARGIN + (i / max_time) * (canvas_width - LEFT_MARGIN - 5)
            self.timeline_canvas.create_line(x, axis_y, x, axis_y + 5, fill='#333')
            self.timeline_canvas.create_text(
                x, axis_y + 13, text=str(i), font=('Arial', 7), fill='#333')
    
    def update_process_combo(self):
        """Update the process timeline combo box"""
        if not self.timeline_process_combo:
            return
        
        process_names = [p.name for p in self.simulator.processes]
        self.timeline_process_combo['values'] = process_names
    
    def update_process_timeline(self):
        """Update the selected process timeline"""
        selected_name = self.timeline_process_var.get()
        if not selected_name:
            return
        
        # Find the process
        process = next((p for p in self.simulator.processes if p.name == selected_name), None)
        if not process:
            return
        
        # Update canvas
        self.state_timeline_canvas.delete('all')
        
        view_width = self.state_timeline_canvas.winfo_width()
        height = self.state_timeline_canvas.winfo_height()
        
        if view_width <= 1:
            view_width = 600
        if height <= 1:
            height = 200
        
        # Apply zoom
        zoom = getattr(self, 'state_zoom_var', None)
        zoom = zoom.get() if zoom else 1.0
        canvas_width = max(view_width, int(view_width * zoom))
        self.state_timeline_canvas.configure(scrollregion=(0, 0, canvas_width, height))
        
        # Calculate time scale
        max_time = max(process.completion_time, 100)
        
        # Draw state timeline
        y = 30
        bar_height = 40
        
        # Draw process name and info
        self.state_timeline_canvas.create_text(10, 15, text=f"Process: {process.name} (PID: {process.pid})", font=('Arial', 10, 'bold'))
        self.state_timeline_canvas.create_text(canvas_width - 150, 15, text=f"Burst: {process.burst_time} | Priority: {process.priority}", font=('Arial', 9))
        
        # Draw execution blocks from gantt chart
        process_bursts = [g for g in self.simulator.gantt_chart if g['pid'] == process.pid]
        
        for burst in process_bursts:
            start_x = (burst['start'] / max_time) * (canvas_width - 80) + 80
            end_x = (burst['end'] / max_time) * (canvas_width - 80) + 80
            bar_width = end_x - start_x
            
            if bar_width > 0:
                self.state_timeline_canvas.create_rectangle(
                    start_x, y, end_x, y + bar_height,
                    fill=burst['color'], outline='black'
                )
                self.state_timeline_canvas.create_text(
                    start_x + bar_width/2, y + bar_height/2,
                    text=f"{burst['start']}-{burst['end']}", fill='white', font=('Arial', 8)
                )
        
        # Draw time axis
        axis_y = y + bar_height + 10
        self.state_timeline_canvas.create_line(80, axis_y, canvas_width - 10, axis_y, arrow=tk.LAST)
        
        # Time markers
        for i in range(0, int(max_time) + 1, max(1, int(max_time / 10))):
            x = (i / max_time) * (canvas_width - 80) + 80
            self.state_timeline_canvas.create_line(x, axis_y, x, axis_y + 5)
            self.state_timeline_canvas.create_text(x, axis_y + 15, text=str(i), font=('Arial', 7))
        
        # Update state details text
        self.state_details_text.config(state=tk.NORMAL)
        self.state_details_text.delete(1.0, tk.END)
        
        self.state_details_text.insert(tk.END, f"Process: {process.name}\n")
        self.state_details_text.insert(tk.END, f"PID: {process.pid}\n")
        self.state_details_text.insert(tk.END, f"Arrival Time: {process.arrival_time}\n")
        self.state_details_text.insert(tk.END, f"Burst Time: {process.burst_time}\n")
        self.state_details_text.insert(tk.END, f"Priority: {process.priority}\n")
        self.state_details_text.insert(tk.END, f"Start Time: {process.start_time}\n")
        self.state_details_text.insert(tk.END, f"Completion Time: {process.completion_time}\n")
        self.state_details_text.insert(tk.END, f"Waiting Time: {process.waiting_time}\n")
        self.state_details_text.insert(tk.END, f"Turnaround Time: {process.turnaround_time}\n")
        self.state_details_text.insert(tk.END, f"Response Time: {process.response_time}\n")
        self.state_details_text.insert(tk.END, f"Current State: {process.state.value}\n\n")
        
        self.state_details_text.insert(tk.END, "State Transitions:\n")
        for time, state in process.state_history:
            self.state_details_text.insert(tk.END, f"  Time {time}: {state.value}\n")
        
        self.state_details_text.config(state=tk.DISABLED)
    
    def update_process_table(self):
        """Update the process list table"""
        # Clear existing items
        for item in self.process_tree.get_children():
            self.process_tree.delete(item)
        
        # Add processes
        for process in self.simulator.processes:
            self.process_tree.insert('', tk.END, values=(
                process.pid,
                process.name,
                process.arrival_time,
                process.burst_time,
                process.memory_required,
                process.priority,
                process.state.value,
                process.remaining_burst
            ))
    
    def update_gantt_chart(self):
        """Update the Gantt chart"""
        if not self.gantt_canvas:
            return
            
        self.gantt_canvas.delete('all')
        
        if not self.simulator.gantt_chart:
            return
        
        # Canvas dimensions
        try:
            self.gantt_canvas.update_idletasks()
        except:
            pass
        
        view_width = self.gantt_canvas.winfo_width()
        height = self.gantt_canvas.winfo_height()
        
        if view_width <= 1:
            view_width = 700
        if height <= 1:
            height = 200
        
        # Apply zoom – virtual canvas wider than view
        zoom = getattr(self, 'gantt_zoom_var', None)
        zoom = zoom.get() if zoom else 1.0
        canvas_width = max(view_width, int(view_width * zoom))
        
        # Calculate time scale
        max_time = max((g['end'] for g in self.simulator.gantt_chart), default=100)
        if max_time == 0:
            max_time = 100
        
        # Set scroll region to full virtual width
        self.gantt_canvas.configure(scrollregion=(0, 0, canvas_width, height))
        
        # Draw Gantt chart
        y = height / 2 - 20
        bar_height = 40
        
        for i, entry in enumerate(self.simulator.gantt_chart):
            start_x = (entry['start'] / max_time) * (canvas_width - 50) + 50
            end_x = (entry['end'] / max_time) * (canvas_width - 50) + 50
            bar_width = end_x - start_x
            
            if bar_width > 0:
                # Draw bar
                self.gantt_canvas.create_rectangle(
                    start_x, y, end_x, y + bar_height,
                    fill=entry['color'], outline='black'
                )
                
                # Draw process name
                if bar_width > 30:
                    self.gantt_canvas.create_text(
                        start_x + bar_width / 2, y + bar_height / 2,
                        text=entry['process'], fill='white'
                    )
        
        # Draw time axis
        self.gantt_canvas.create_line(50, y + bar_height + 5, canvas_width - 10, y + bar_height + 5, arrow=tk.LAST)
        
        # Draw time markers
        step = max(1, int(max_time / 10))
        for i in range(0, int(max_time) + 1, step):
            x = (i / max_time) * (canvas_width - 50) + 50
            self.gantt_canvas.create_line(x, y + bar_height + 5, x, y + bar_height + 10)
            self.gantt_canvas.create_text(x, y + bar_height + 20, text=str(i))
        
        # Update time label
        self.time_label.config(text=f"Current Time: {self.simulator.scheduler.current_time}")
    
    def update_metrics(self):
        """Update the metrics display"""
        metrics = self.simulator.get_metrics()
        
        # Update Dashboard Cards
        if hasattr(self, 'avg_wait_label') and self.avg_wait_label:
            self.avg_wait_label.configure(text=f"{metrics['avg_waiting_time']:.2f}")
        if hasattr(self, 'avg_ta_label') and self.avg_ta_label:
            self.avg_ta_label.configure(text=f"{metrics['avg_turnaround_time']:.2f}")
        if hasattr(self, 'cpu_util_label') and self.cpu_util_label:
            self.cpu_util_label.configure(text=f"{metrics['cpu_utilization']:.2f}%")
        if hasattr(self, 'mem_util_label') and self.mem_util_label:
            self.mem_util_label.configure(text=f"{metrics.get('memory_utilization', 0):.2f}%")
            
        self.metrics_text.config(state=tk.NORMAL)
        self.metrics_text.delete(1.0, tk.END)
        
        # Current algorithm
        self.metrics_text.insert(tk.END, f"Algorithm: {self.simulator.scheduler.name}\n")
        self.metrics_text.insert(tk.END, f"Preemptive: {'Yes' if self.simulator.scheduler.is_preemptive else 'No'}\n\n")
        
        # Metrics
        self.metrics_text.insert(tk.END, f"Average Waiting Time: {metrics['avg_waiting_time']:.2f} units\n")
        self.metrics_text.insert(tk.END, f"Average Turnaround Time: {metrics['avg_turnaround_time']:.2f} units\n")
        self.metrics_text.insert(tk.END, f"CPU Utilization: {metrics['cpu_utilization']:.2f}%\n")
        self.metrics_text.insert(tk.END, f"Memory Utilization: {metrics.get('memory_utilization', 0):.2f}%\n")
        self.metrics_text.insert(tk.END, f"Throughput: {metrics['throughput']:.2f} processes/unit\n")
        self.metrics_text.insert(tk.END, f"Completed Processes: {metrics['completed_count']}\n\n")
        
        # Process completion order
        self.metrics_text.insert(tk.END, "Process Completion Order:\n")
        for i, p in enumerate(self.simulator.scheduler.completed_processes):
            self.metrics_text.insert(tk.END, f"  {i+1}. {p.name} (PID: {p.pid}) - Completion: {p.completion_time}\n")
        
        self.metrics_text.config(state=tk.DISABLED)
        
        # Update execution log in scheduling details tab
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        
        # Add timeline log entries
        self.log_text.insert(tk.END, "=== TIMELINE LOG ===\n\n")
        
        for entry in self.simulator.timeline_log:
            time = entry.get('time', 0)
            event = entry.get('event', '')
            process = entry.get('process', '')
            pid = entry.get('pid', 0)
            
            if event == 'CPU_BURST_START':
                self.log_text.insert(tk.END, f"[T={time}] {process} (PID:{pid}) - Started CPU burst\n")
            elif event == 'CPU_BURST_END':
                remaining = entry.get('remaining', 0)
                if remaining > 0:
                    self.log_text.insert(tk.END, f"[T={time}] {process} (PID:{pid}) - CPU burst ended, {remaining} remaining\n")
                else:
                    self.log_text.insert(tk.END, f"[T={time}] {process} (PID:{pid}) - CPU burst completed\n")
            elif event == 'PROCESS_TERMINATED':
                wait = entry.get('waiting_time', 0)
                turn = entry.get('turnaround_time', 0)
                self.log_text.insert(tk.END, f"[T={time}] {process} (PID:{pid}) - TERMINATED | Wait: {wait}, Turnaround: {turn}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def update_memory_visualization(self):
        """Update the memory visualization canvas and allocation table"""
        if not self.memory_canvas:
            return
            
        # Update Live Swapping / Admissions event listbox
        if hasattr(self, 'mem_event_listbox') and self.mem_event_listbox:
            self.mem_event_listbox.delete(0, tk.END)
            mem_manager = self.simulator.memory_manager
            # Show last 30 events to avoid overflow and preserve performance
            for event in mem_manager.events[-30:]:
                self.mem_event_listbox.insert(tk.END, f" {event}")
            self.mem_event_listbox.see(tk.END)
            
        self.memory_canvas.delete('all')
        
        try:
            self.memory_canvas.update_idletasks()
        except:
            pass
            
        width = self.memory_canvas.winfo_width()
        height = self.memory_canvas.winfo_height()
        
        if width <= 1: width = 800
        if height <= 1: height = 130
        
        mem_manager = self.simulator.memory_manager
        total_mem = mem_manager.total_memory
        
        if total_mem == 0:
            return
            
        x_offset = 20
        y_offset = 20
        
        # Refresh allocation table
        if hasattr(self, 'mem_table'):
            for row in self.mem_table.get_children():
                self.mem_table.delete(row)
                
        if not mem_manager.paging_enabled:
            # --- CONTIGUOUS MEMORY PATH ---
            bar_height = max(40, height - 40)
            bar_width = width - 40
            
            # Draw title
            self.memory_canvas.create_text(x_offset, y_offset - 10,
                text=f"RAM: {total_mem} MB", anchor=tk.W, font=('Arial', 9, 'bold'), fill='white')
            
            # Draw background bar (free)
            self.memory_canvas.create_rectangle(
                x_offset, y_offset, x_offset + bar_width, y_offset + bar_height,
                fill=COLORS['background'], outline=COLORS['surface_light'], width=2)
            
            free_space = 0
            allocated_space = 0
            
            for idx, block in enumerate(mem_manager.blocks):
                start_x = x_offset + (block.start_address / total_mem) * bar_width
                end_x   = x_offset + ((block.start_address + block.size) / total_mem) * bar_width
                mid_x   = (start_x + end_x) / 2
                
                if block.is_free:
                    free_space += block.size
                    if block.size > total_mem * 0.04:
                        self.memory_canvas.create_text(
                            mid_x, y_offset + bar_height / 2,
                            text=f"Free\n{block.size} MB", font=('Arial', 8), fill=COLORS['light_text'])
                    if hasattr(self, 'mem_table'):
                        self.mem_table.insert('', tk.END, values=(
                            idx + 1, block.start_address, block.size, '—', 'FREE'))
                else:
                    allocated_space += block.size
                    color = self.simulator._get_process_color(block.process_pid)
                    process = next((p for p in self.simulator.processes if p.pid == block.process_pid), None)
                    p_name = process.name if process else f"PID {block.process_pid}"
                    state  = process.state.value if process else '?'
                    
                    self.memory_canvas.create_rectangle(
                        start_x, y_offset, end_x, y_offset + bar_height,
                        fill=color, outline=COLORS['surface_light'])
                    if (end_x - start_x) > 25:
                        self.memory_canvas.create_text(
                            mid_x, y_offset + bar_height / 2,
                            text=f"{p_name}\n{block.size} MB",
                            font=('Arial', 8, 'bold'), fill='white')
                    if hasattr(self, 'mem_table'):
                        self.mem_table.insert('', tk.END, values=(
                            idx + 1, block.start_address, block.size, p_name, f'ALLOCATED ({state})'),
                            tags=('alloc',))
                        self.mem_table.tag_configure('alloc', background=COLORS['surface'], foreground='white')
                        
            fragmentation = mem_manager.get_fragmentation()
            if self.memory_stats_label:
                util_pct = round(allocated_space / total_mem * 100, 1) if total_mem else 0
                self.memory_stats_label.config(
                    text=f"Total: {total_mem} MB  |  Allocated: {allocated_space} MB ({util_pct}%)  "
                         f"|  Free: {free_space} MB  |  Fragmentation: {fragmentation} MB")
        else:
            # --- VIRTUAL MEMORY PAGING PATH ---
            bar_height = 35
            bar_width = width - 40
            
            # Draw RAM frames title
            self.memory_canvas.create_text(x_offset, y_offset - 10,
                text=f"Physical RAM Frames (Page Size: {mem_manager.page_size} MB)", 
                anchor=tk.W, font=('Arial', 9, 'bold'), fill='white')
                
            num_frames = len(mem_manager.frames)
            frame_width = bar_width / max(1, num_frames)
            
            allocated_space = 0
            
            # Draw physical frame grid
            for idx in range(num_frames):
                start_x = x_offset + idx * frame_width
                end_x = x_offset + (idx + 1) * frame_width
                mid_x = (start_x + end_x) / 2
                
                frame_info = mem_manager.frames[idx]
                if frame_info is None:
                    # Free Frame
                    self.memory_canvas.create_rectangle(
                        start_x, y_offset, end_x, y_offset + bar_height,
                        fill=COLORS['background'], outline=COLORS['surface_light'], width=1)
                    if frame_width > 30:
                        self.memory_canvas.create_text(
                            mid_x, y_offset + bar_height / 2,
                            text=f"F{idx}\nFree", font=('Arial', 7), fill=COLORS['light_text'])
                    if hasattr(self, 'mem_table'):
                        self.mem_table.insert('', tk.END, values=(
                            f"Frame {idx}", idx * mem_manager.page_size, mem_manager.page_size, '—', 'FREE FRAME'))
                else:
                    # Allocated Frame
                    allocated_space += mem_manager.page_size
                    pid = frame_info['pid']
                    page_num = frame_info['page']
                    
                    color = self.simulator._get_process_color(pid)
                    process = next((p for p in self.simulator.processes if p.pid == pid), None)
                    p_name = process.name if process else f"PID {pid}"
                    state = process.state.value if process else '?'
                    
                    self.memory_canvas.create_rectangle(
                        start_x, y_offset, end_x, y_offset + bar_height,
                        fill=color, outline=COLORS['surface_light'], width=1)
                    
                    if frame_width > 30:
                        self.memory_canvas.create_text(
                            mid_x, y_offset + bar_height / 2,
                            text=f"{p_name}\n[Pg {page_num}]", font=('Arial', 7, 'bold'), fill='white')
                    if hasattr(self, 'mem_table'):
                        self.mem_table.insert('', tk.END, values=(
                            f"Frame {idx}", idx * mem_manager.page_size, mem_manager.page_size, p_name, f'ALLOCATED (Page {page_num} - {state})'),
                            tags=('alloc',))
                        self.mem_table.tag_configure('alloc', background=COLORS['surface'], foreground='white')
            
            # Draw Swap Disk Area below the RAM grid
            swap_y_offset = y_offset + bar_height + 25
            self.memory_canvas.create_text(x_offset, swap_y_offset - 10,
                text="Virtual Disk Swap Space (Evicted Pages)", anchor=tk.W, font=('Arial', 9, 'bold'), fill='white')
            
            # Draw Swap Space Background Bar
            self.memory_canvas.create_rectangle(
                x_offset, swap_y_offset, x_offset + bar_width, swap_y_offset + 30,
                fill=COLORS['background'], outline=COLORS['surface_light'], width=1)
                
            if not mem_manager.swap_space:
                self.memory_canvas.create_text(
                    x_offset + bar_width / 2, swap_y_offset + 15,
                    text="No pages swapped to disk", font=('Arial', 8, 'italic'), fill=COLORS['light_text'])
            else:
                # Draw small cards for each swapped page
                swap_item_width = 60
                swap_item_height = 24
                swap_gap = 5
                
                for idx, (slot, info) in enumerate(sorted(mem_manager.swap_space.items())):
                    pid = info['pid']
                    page_num = info['page']
                    
                    start_x = x_offset + 5 + idx * (swap_item_width + swap_gap)
                    # Don't draw past canvas width
                    if start_x + swap_item_width > x_offset + bar_width:
                        self.memory_canvas.create_text(
                            x_offset + bar_width - 25, swap_y_offset + 15,
                            text="...", font=('Arial', 10, 'bold'), fill=COLORS['light_text'])
                        break
                        
                    color = self.simulator._get_process_color(pid)
                    process = next((p for p in self.simulator.processes if p.pid == pid), None)
                    p_name = process.name if process else f"PID {pid}"
                    
                    self.memory_canvas.create_rectangle(
                        start_x, swap_y_offset + 3, start_x + swap_item_width, swap_y_offset + 3 + swap_item_height,
                        fill=color, outline=COLORS['surface_light'], width=1)
                        
                    self.memory_canvas.create_text(
                        start_x + swap_item_width / 2, swap_y_offset + 3 + swap_item_height / 2,
                        text=f"{p_name}:P{page_num}", font=('Arial', 7, 'bold'), fill='white')
                        
                    if hasattr(self, 'mem_table'):
                        self.mem_table.insert('', tk.END, values=(
                            f"Swap Slot {slot}", '—', mem_manager.page_size, p_name, 'SWAPPED OUT (On Disk)'),
                            tags=('swap',))
                        self.mem_table.tag_configure('swap', background='#422020', foreground='white')
                        
            free_space = total_mem - allocated_space
            page_faults = mem_manager.total_page_faults
            if self.memory_stats_label:
                util_pct = round(allocated_space / total_mem * 100, 1) if total_mem else 0
                self.memory_stats_label.config(
                    text=f"Total: {total_mem} MB  |  Allocated: {allocated_space} MB ({util_pct}%)  "
                         f"|  Free: {free_space} MB  |  Total Page Faults: {page_faults}")             

    def create_analytics_tab(self):
        """Create the premium dark analytics tab with comparative Matplotlib charts"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Analytics Dashboard")
        
        # Main vertical frame
        main_frame = ttk.Frame(tab, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title & Info card
        info_frame = ttk.LabelFrame(main_frame, text="Dynamic Benchmarking Workstation", padding=10)
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        info_label = ttk.Label(info_frame, 
            text="Simulate different scheduling strategies (e.g. FCFS, Round Robin, Linux CFS, EDF) to automatically compare performance metrics below in real-time.",
            font=('Helvetica', 10, 'italic'), foreground=COLORS['light_text'])
        info_label.pack(fill=tk.X)
        
        # Chart container frame
        self.chart_frame = ttk.Frame(main_frame)
        self.chart_frame.pack(fill=tk.BOTH, expand=True)
        
        if not MATPLOTLIB_AVAILABLE:
            no_lib_label = tk.Label(self.chart_frame,
                text="📊 Matplotlib is not installed.\n\nRun 'pip install matplotlib' to unlock real-time comparative charts.",
                font=('Helvetica', 12, 'bold'), bg=COLORS['surface'], fg=COLORS['warning'], justify=tk.CENTER)
            no_lib_label.pack(fill=tk.BOTH, expand=True, pady=40)
        else:
            self.update_analytics_charts()

    def update_analytics_charts(self):
        """Redraw comparison charts based on benchmark_history"""
        if not MATPLOTLIB_AVAILABLE or not hasattr(self, 'chart_frame'):
            return
            
        # Clear chart frame
        for widget in self.chart_frame.winfo_children():
            widget.destroy()
            
        if not self.benchmark_history:
            no_data_label = tk.Label(self.chart_frame,
                text="⌛ No benchmarking history recorded yet.\n\nRun a complete simulation to generate comparative charts here automatically!",
                font=('Helvetica', 11, 'italic'), bg=COLORS['surface'], fg=COLORS['light_text'])
            no_data_label.pack(fill=tk.BOTH, expand=True, pady=40)
            return
            
        # Draw Side-by-Side Subplots using Matplotlib!
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4), facecolor=COLORS['surface'])
        
        algorithms = list(self.benchmark_history.keys())
        avg_wait = [self.benchmark_history[a]['avg_waiting_time'] for a in algorithms]
        avg_turn = [self.benchmark_history[a]['avg_turnaround_time'] for a in algorithms]
        page_faults = [self.benchmark_history[a]['page_faults'] for a in algorithms]
        
        text_color = COLORS['text']
        
        # Subplot 1: Waiting & Turnaround times
        x = range(len(algorithms))
        width = 0.35
        
        ax1.set_facecolor(COLORS['background'])
        ax1.bar([i - width/2 for i in x], avg_wait, width, label='Avg Waiting Time', color=COLORS['primary'])
        ax1.bar([i + width/2 for i in x], avg_turn, width, label='Avg Turnaround Time', color=COLORS['secondary'])
        
        ax1.set_title("Latency Benchmarks (Ticks)", color=text_color, fontsize=10, fontweight='bold')
        ax1.set_xticks(x)
        ax1.set_xticklabels(algorithms, color=text_color, rotation=15, fontsize=8)
        ax1.tick_params(axis='y', colors=text_color)
        ax1.legend(facecolor=COLORS['surface'], labelcolor=text_color, fontsize=8)
        ax1.grid(True, color=COLORS['surface_light'], alpha=0.3)
        
        # Subplot 2: Page Faults
        ax2.set_facecolor(COLORS['background'])
        ax2.bar(algorithms, page_faults, width=0.4, label='Page Faults', color=COLORS['accent'])
        
        ax2.set_title("System Page Faults", color=text_color, fontsize=10, fontweight='bold')
        ax2.tick_params(axis='x', colors=text_color, labelrotation=15, labelsize=8)
        ax2.tick_params(axis='y', colors=text_color)
        ax2.legend(facecolor=COLORS['surface'], labelcolor=text_color, fontsize=8)
        ax2.grid(True, color=COLORS['surface_light'], alpha=0.3)
        
        # Tight layout to avoid overlapping
        fig.tight_layout()
        
        # Embed Figure inside Tkinter Canvas
        canvas = FigureCanvasTkAgg(fig, master=self.chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        plt.close(fig) # Prevent memory leaks!             

    def change_theme(self):
        """Handle theme transition, updating all styles and dynamically restyling standard widgets"""
        theme_name = self.theme_var.get()
        if theme_name not in THEMES:
            return
            
        global COLORS
        COLORS.update(THEMES[theme_name])
        
        # Configure root window background
        self.root.configure(bg=COLORS['background'])
        
        # Re-apply ttk themes dynamically
        style = ttk.Style()
        style.theme_use('clam')
        
        style.configure('.', background=COLORS['background'], foreground=COLORS['text'])
        style.configure('TFrame', background=COLORS['background'])
        style.configure('TLabel', background=COLORS['background'], foreground=COLORS['text'])
        style.configure('TLabelframe', background=COLORS['background'], bordercolor=COLORS['surface_light'])
        style.configure('TLabelframe.Label', background=COLORS['background'], foreground=COLORS['secondary'], font=('Helvetica', 10, 'bold'))
        
        is_light = (theme_name == "Solarized Light")
        input_fg = COLORS['text'] if is_light else 'white'
        button_fg = 'white' if not is_light else '#fdf6e3'
        heading_fg = 'white' if not is_light else '#073642'
        
        # Update buttons
        style.configure('TButton', background=COLORS['primary'], foreground=button_fg, borderwidth=0, font=('Helvetica', 9, 'bold'))
        style.map('TButton', background=[('active', COLORS['secondary'])], foreground=[('active', button_fg)])
        
        # Update notebook tabs
        style.configure('TNotebook', background=COLORS['background'], borderwidth=0)
        style.configure('TNotebook.Tab', background=COLORS['surface'], foreground=COLORS['light_text'], font=('Helvetica', 9, 'bold'), padding=(15, 6))
        style.map('TNotebook.Tab', background=[('selected', COLORS['primary'])], foreground=[('selected', button_fg)])
        
        # Update entries, spinboxes, and comboboxes
        style.configure('TEntry', fieldbackground=COLORS['surface'], foreground=input_fg, bordercolor=COLORS['surface_light'])
        style.configure('TSpinbox', fieldbackground=COLORS['surface'], foreground=input_fg, bordercolor=COLORS['surface_light'])
        style.configure('TCombobox', fieldbackground=COLORS['surface'], foreground=input_fg, bordercolor=COLORS['surface_light'])
        
        # Update tables
        style.configure('Treeview', background=COLORS['surface'], foreground=COLORS['text'], fieldbackground=COLORS['surface'], font=('Helvetica', 9), rowheight=24)
        style.configure('Treeview.Heading', background=COLORS['surface_light'], foreground=heading_fg, font=('Helvetica', 9, 'bold'))
        style.map('Treeview', background=[('selected', COLORS['primary'])], foreground=[('selected', button_fg)])
        
        # Recursively restyle standard Tk widgets
        self._restyle_widgets(self.root)
        
        # Force full visual redraw of Gantt, Timelines, Memory block frames, and comparative analytics charts!
        self.update_display()
        self.update_analytics_charts()
        
        # Redraw color swatch preview next to combo
        self.draw_theme_swatch()
        
        # Persist theme choice
        self.save_config()

    def _restyle_widgets(self, widget):
        """Recursively update standard tk widgets to match the new theme colors"""
        try:
            w_class = widget.winfo_class()
        except:
            return
            
        if w_class == 'Label' and not isinstance(widget, ttk.Label):
            if widget == self.title_label:
                widget.configure(bg=COLORS['background'], fg=COLORS['secondary'])
            else:
                widget.configure(bg=COLORS['background'], fg=COLORS['text'])
                
        elif w_class == 'Canvas':
            widget.configure(bg=COLORS['surface'])
            
        elif w_class == 'Text':
            widget.configure(bg=COLORS['surface'], fg=COLORS['text'], insertbackground=COLORS['text'])
            
        # Recurse over children
        for child in widget.winfo_children():
            self._restyle_widgets(child)

    def load_config(self):
        """Load user configurations like selected theme and onboarding visibility"""
        import json
        import os
        if os.path.exists("config.json"):
            try:
                with open("config.json", "r") as f:
                    config = json.load(f)
                    theme = config.get("theme", "Slate Dark")
                    if theme in THEMES:
                        global COLORS
                        COLORS.update(THEMES[theme])
                        self.theme_var = tk.StringVar(value=theme)
                    else:
                        self.theme_var = tk.StringVar(value="Slate Dark")
                    self.onboarding_visible = config.get("onboarding_visible", True)
            except Exception as e:
                print(f"Error loading config: {e}")
                self.theme_var = tk.StringVar(value="Slate Dark")
                self.onboarding_visible = True
        else:
            self.theme_var = tk.StringVar(value="Slate Dark")
            self.onboarding_visible = True

    def save_config(self):
        """Save theme selection and onboarding visibility to config.json"""
        import json
        try:
            config = {
                "theme": self.theme_var.get() if hasattr(self, 'theme_var') else "Slate Dark",
                "onboarding_visible": self.onboarding_visible
            }
            with open("config.json", "w") as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            print(f"Error saving config: {e}")

    def create_onboarding_panel(self, parent):
        """Create a beautiful onboarding / help guide panel"""
        self.onboarding_frame = ttk.LabelFrame(parent, text="Welcome & Quick Start Guide", padding=10)
        
        lbl_title = ttk.Label(
            self.onboarding_frame,
            text="How to Use the Interactive CPU Scheduling Simulator",
            font=("Helvetica", 11, "bold")
        )
        lbl_title.pack(anchor=tk.W, pady=(0, 5))
        
        guide_text = (
            "• Add Processes: Specify Name, Arrival Time, Burst Time, and optional Memory/Period/Deadline. Click 'Add Process'.\n"
            "• Select Schedulers: Pick traditional (FCFS, SJF, Priority, RR, MLFQ) or RT/Advanced (CFS, RMS, EDF) algorithms.\n"
            "• Simulation Controls: Click 'Start' to run continuously, 'Pause' to suspend, or 'Step' to inspect one transition.\n"
            "• Memory & Analytics: Explore Virtual Memory Frames map under Memory Tab, and view dynamic bar charts in the Analytics Tab."
        )
        
        lbl_body = ttk.Label(
            self.onboarding_frame,
            text=guide_text,
            font=("Helvetica", 9),
            justify=tk.LEFT
        )
        lbl_body.pack(anchor=tk.W, pady=(0, 10))
        
        btn_frame = ttk.Frame(self.onboarding_frame)
        btn_frame.pack(anchor=tk.E)
        
        dismiss_btn = ttk.Button(btn_frame, text="Got it, Hide Guide", command=self.dismiss_onboarding)
        dismiss_btn.pack(side=tk.RIGHT)

    def dismiss_onboarding(self):
        """Dismiss/hide the onboarding panel and save setting"""
        self.onboarding_visible = False
        if self.onboarding_frame:
            self.onboarding_frame.pack_forget()
        self.save_config()

    def toggle_onboarding(self):
        """Toggle the onboarding panel visibility"""
        self.onboarding_visible = not self.onboarding_visible
        if self.onboarding_visible:
            self.onboarding_frame.pack(fill=tk.X, after=self.header_frame, pady=(0, 15))
        else:
            self.onboarding_frame.pack_forget()
        self.save_config()

    def create_presets_panel(self, parent):
        """Create the workload presets and import/export panel"""
        frame = ttk.LabelFrame(parent, text="Workload Presets & Portability", padding=10)
        
        # Presets Title
        ttk.Label(frame, text="Deterministic Workload Presets:", font=("Helvetica", 9, "bold")).pack(anchor=tk.W, pady=(0, 5))
        
        preset_btn_frame = ttk.Frame(frame)
        preset_btn_frame.pack(fill=tk.X, pady=(0, 10))
        
        cpu_btn = ttk.Button(preset_btn_frame, text="CPU-Bound", command=lambda: self.load_preset("CPU"))
        cpu_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        self.control_widgets.append(cpu_btn)
        
        io_btn = ttk.Button(preset_btn_frame, text="I/O-Bound", command=lambda: self.load_preset("IO"))
        io_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        self.control_widgets.append(io_btn)
        
        mixed_btn = ttk.Button(preset_btn_frame, text="Mixed", command=lambda: self.load_preset("Mixed"))
        mixed_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        self.control_widgets.append(mixed_btn)
        
        # Separator line
        ttk.Separator(frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)
        
        # Import/Export Title
        ttk.Label(frame, text="Workload Portability (JSON):", font=("Helvetica", 9, "bold")).pack(anchor=tk.W, pady=(0, 5))
        
        port_btn_frame = ttk.Frame(frame)
        port_btn_frame.pack(fill=tk.X)
        
        imp_btn = ttk.Button(port_btn_frame, text="Import Workload", command=self.import_workload)
        imp_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        self.control_widgets.append(imp_btn)
        
        exp_btn = ttk.Button(port_btn_frame, text="Export Workload", command=self.export_workload)
        exp_btn.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=2)
        self.control_widgets.append(exp_btn)
        
        return frame

    def load_preset(self, preset_type):
        """Load CPU-bound, I/O-bound, or Mixed workloads"""
        self.simulator.reset()
        self.simulator.processes = []
        
        import random
        # Seed to keep it deterministic but clean
        random.seed(42)
        
        if preset_type == "CPU":
            for i in range(5):
                p = Process(
                    pid=f"CPU_P{i+1}",
                    name=f"CPU_P{i+1}",
                    arrival_time=i * 2,
                    burst_time=random.randint(15, 30),
                    priority=random.randint(1, 5),
                    memory_required=random.randint(50, 150)
                )
                self.simulator.processes.append(p)
        elif preset_type == "IO":
            for i in range(6):
                p = Process(
                    pid=f"IO_P{i+1}",
                    name=f"IO_P{i+1}",
                    arrival_time=i,
                    burst_time=random.randint(3, 8),
                    priority=random.randint(1, 5),
                    memory_required=random.randint(30, 80),
                    is_io_bound=True
                )
                self.simulator.processes.append(p)
        else: # Mixed
            for i in range(3):
                p_cpu = Process(
                    pid=f"MIX_CPU{i+1}",
                    name=f"MIX_CPU{i+1}",
                    arrival_time=i * 3,
                    burst_time=random.randint(12, 20),
                    priority=random.randint(1, 5),
                    memory_required=random.randint(100, 200)
                )
                p_io = Process(
                    pid=f"MIX_IO{i+1}",
                    name=f"MIX_IO{i+1}",
                    arrival_time=i * 3 + 1,
                    burst_time=random.randint(3, 6),
                    priority=random.randint(1, 5),
                    memory_required=random.randint(30, 70),
                    is_io_bound=True
                )
                self.simulator.processes.extend([p_cpu, p_io])
                
        self.update_process_table()
        self.update_display()
        messagebox.showinfo("Preset Loaded", f"Loaded a pre-configured {preset_type}-bound workload preset!")

    def export_workload(self):
        """Export current process list to JSON"""
        from tkinter import filedialog
        import json
        import os
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        if not file_path:
            return
            
        try:
            workload_data = [p.to_dict() for p in self.simulator.processes]
            with open(file_path, 'w') as f:
                json.dump(workload_data, f, indent=4)
            messagebox.showinfo("Success", f"Workload successfully exported to {os.path.basename(file_path)}!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export workload: {e}")

    def import_workload(self):
        """Import process list from JSON"""
        from tkinter import filedialog
        import json
        import os
        file_path = filedialog.askopenfilename(
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        if not file_path:
            return
            
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            self.simulator.reset()
            self.simulator.processes = []
            
            for item in data:
                p = Process(
                    pid=item.get('pid'),
                    name=item.get('name', item.get('pid')),
                    arrival_time=item.get('arrival_time', 0),
                    burst_time=item.get('burst_time', 5),
                    priority=item.get('priority', 5),
                    memory_required=item.get('memory_required', 100),
                    period=item.get('period'),
                    deadline=item.get('deadline'),
                    nice=item.get('nice', 0),
                    is_io_bound=item.get('is_io_bound', False)
                )
                self.simulator.processes.append(p)
                
            self.update_process_table()
            self.update_display()
            messagebox.showinfo("Success", f"Workload successfully imported from {os.path.basename(file_path)}!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to import workload: {e}")

    def set_control_states(self, enabled=True):
        """Enable or disable input and configuration controls to prevent mid-simulation changes"""
        state_str = "normal" if enabled else "disabled"
        for w in self.control_widgets:
            try:
                if isinstance(w, ttk.Combobox):
                    w.configure(state="readonly" if enabled else "disabled")
                else:
                    w.configure(state=state_str)
            except Exception as e:
                try:
                    w['state'] = state_str
                except:
                    pass

    def update_simulation_state(self):
        """Update the bold colored state label and handle control locks"""
        if not hasattr(self, 'state_indicator_var') or not self.state_indicator_var:
            return
            
        is_running = self.simulator.is_running
        is_paused = self.simulator.is_paused
        
        # Check for real-time deadline misses/overruns that act as system deadlocks/failures
        rt_deadlock = False
        if hasattr(self.simulator.scheduler, 'missed_deadlines') and self.simulator.scheduler.missed_deadlines:
            rt_deadlock = True
            
        if rt_deadlock:
            self.state_indicator_var.set("Deadlock")
            self.state_label.configure(fg=COLORS['error'])
            self.set_control_states(True)
        elif is_running and not is_paused:
            all_done = len(self.simulator.processes) > 0 and all(p.state == ProcessState.TERMINATED for p in self.simulator.processes)
            if all_done:
                self.state_indicator_var.set("Completed")
                self.state_label.configure(fg=COLORS['secondary'])
                self.set_control_states(True)
            else:
                self.state_indicator_var.set("Running")
                self.state_label.configure(fg=COLORS['secondary'])
                self.set_control_states(False)
        elif is_running and is_paused:
            self.state_indicator_var.set("Paused")
            self.state_label.configure(fg=COLORS['warning'])
            self.set_control_states(True)
        else:
            all_done = len(self.simulator.processes) > 0 and all(p.state == ProcessState.TERMINATED for p in self.simulator.processes)
            if all_done:
                self.state_indicator_var.set("Completed")
                self.state_label.configure(fg=COLORS['secondary'])
                self.set_control_states(True)
            else:
                self.state_indicator_var.set("Ready")
                self.state_label.configure(fg=COLORS['success'])
                self.set_control_states(True)

    def export_metrics_data(self):
        """Export current performance metrics to JSON or CSV"""
        from tkinter import filedialog
        import json
        import csv
        import os
        
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json"), ("CSV Files", "*.csv"), ("All Files", "*.*")]
        )
        if not file_path:
            return
            
        metrics = self.simulator.get_metrics()
        
        try:
            if file_path.endswith('.csv'):
                with open(file_path, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(["Metric", "Value"])
                    writer.writerow(["Algorithm", self.simulator.scheduler.name])
                    writer.writerow(["Average Waiting Time", f"{metrics['avg_waiting_time']:.2f}"])
                    writer.writerow(["Average Turnaround Time", f"{metrics['avg_turnaround_time']:.2f}"])
                    writer.writerow(["CPU Utilization", f"{metrics['cpu_utilization']:.2f}%"])
                    writer.writerow(["Memory Utilization", f"{metrics.get('memory_utilization', 0):.2f}%"])
                    writer.writerow(["Throughput", f"{metrics['throughput']:.2f}"])
                    writer.writerow(["Completed Count", metrics['completed_count']])
            else: # JSON
                with open(file_path, 'w') as f:
                    json.dump(metrics, f, indent=4)
            messagebox.showinfo("Success", f"Metrics successfully exported to {os.path.basename(file_path)}!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export metrics: {e}")

    def view_report_popup(self):
        """View a beautiful, detailed pop-up report summarizing simulator efficiency"""
        metrics = self.simulator.get_metrics()
        
        report_win = tk.Toplevel(self.root)
        report_win.title("Detailed System Performance Report")
        report_win.geometry("500x420")
        report_win.configure(bg=COLORS['background'])
        
        report_win.transient(self.root)
        report_win.grab_set()
        
        title_lbl = tk.Label(
            report_win,
            text="System Performance Report",
            font=("Helvetica", 14, "bold"),
            bg=COLORS['background'],
            fg=COLORS['secondary']
        )
        title_lbl.pack(pady=15)
        
        content_frame = ttk.Frame(report_win, padding=15)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)
        
        details = [
            ("Scheduling Algorithm:", f"{self.simulator.scheduler.name}"),
            ("Preemption Strategy:", "Preemptive" if self.simulator.scheduler.is_preemptive else "Non-Preemptive"),
            ("Completed Tasks:", f"{metrics['completed_count']} processes"),
            ("Average Wait Time:", f"{metrics['avg_waiting_time']:.2f} units"),
            ("Average Turnaround:", f"{metrics['avg_turnaround_time']:.2f} units"),
            ("CPU Utilization:", f"{metrics['cpu_utilization']:.2f}%"),
            ("Memory Utilization:", f"{metrics.get('memory_utilization', 0):.2f}%"),
            ("Throughput Rate:", f"{metrics['throughput']:.2f} proc/unit")
        ]
        
        for i, (label, val) in enumerate(details):
            lbl = ttk.Label(content_frame, text=label, font=("Helvetica", 10, "bold"))
            lbl.grid(row=i, column=0, sticky=tk.W, pady=4, padx=5)
            
            fg_color = COLORS['text']
            try:
                raw_val = val.replace('%','').split()[0]
                if "Utilization" in label or "Completed" in label:
                    fg_color = COLORS['success'] if float(raw_val) > 50 else COLORS['primary']
                elif "Time" in label or "Turnaround" in label:
                    fg_color = COLORS['secondary']
            except:
                pass
                
            val_lbl = tk.Label(content_frame, text=val, font=("Helvetica", 10), bg=COLORS['background'], fg=fg_color)
            val_lbl.grid(row=i, column=1, sticky=tk.W, pady=4, padx=5)
            
        close_btn = ttk.Button(report_win, text="Close Report", command=report_win.destroy)
        close_btn.pack(pady=15)
        
        self._restyle_widgets(report_win)

    def draw_theme_swatch(self):
        """Draw the primary and secondary colors as blocks in the swatch preview canvas"""
        if not hasattr(self, 'theme_swatch_canvas') or not self.theme_swatch_canvas:
            return
        self.theme_swatch_canvas.delete(tk.ALL)
        
        self.theme_swatch_canvas.configure(
            bg=COLORS['background'],
            highlightbackground=COLORS['surface_light']
        )
        
        self.theme_swatch_canvas.create_rectangle(2, 2, 17, 16, fill=COLORS['primary'], outline="")
        self.theme_swatch_canvas.create_rectangle(17, 2, 33, 16, fill=COLORS['secondary'], outline="")

    def reset_theme_to_default(self):
        """Reset simulator theme to default Slate Dark"""
        self.theme_var.set("Slate Dark")
        self.change_theme()


import argparse
import sys

def run_cli_simulation(keep_alive: bool = False):
    """Run a headless simulation for Docker/Resource constraint testing"""
    print("--- OS Scheduling Simulator (CLI Mode) ---")
    simulator = SchedulingSimulator()
    
    # Configure Memory
    simulator.memory_manager.reset(1024)
    simulator.memory_manager.algorithm = MemoryAllocationAlgorithm.BEST_FIT
    
    # Add random processes
    for i in range(1, 21):
        arrival = random.randint(0, 50)
        burst = random.randint(5, 30)
        priority = random.randint(1, 10)
        memory = random.randint(50, 250)
        is_io = random.choice([True, False])
        simulator.add_process(f"P{i}", arrival, burst, priority, is_io, memory)
        
    print(f"Generated 20 processes. Total System Memory: 1024MB")
    print("Starting simulation...")
    
    # Start and run until complete
    simulator.start_simulation()
    
    while simulator.is_running:
        simulator.step_simulation()
        
    print("\n--- Simulation Complete ---")
    metrics = simulator.get_metrics()
    print(f"Average Waiting Time: {metrics['avg_waiting_time']:.2f}")
    print(f"Average Turnaround Time: {metrics['avg_turnaround_time']:.2f}")
    print(f"CPU Utilization: {metrics['cpu_utilization']:.2f}%")
    print(f"Memory Utilization: {metrics.get('memory_utilization', 0):.2f}%")
    print(f"Throughput: {metrics['throughput']:.2f} proc/unit")
    print(f"Completed Processes: {metrics['completed_count']}")
    
    if keep_alive:
        print("\nSimulation finished. Container will remain running for monitoring (press Ctrl+C to exit).")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


def main():
    """Main function to start the application"""
    parser = argparse.ArgumentParser(description="OS Scheduling Simulator")
    parser.add_argument('--cli', action='store_true', help='Run without GUI in headless mode')
    parser.add_argument('--keep-alive', action='store_true', help='Keep CLI simulation running after completion for monitoring')
    args = parser.parse_args()
    
    if args.cli:
        run_cli_simulation(keep_alive=args.keep_alive)
    else:
        root = tk.Tk()
        app = SchedulingSimulatorGUI(root)
        root.mainloop()


if __name__ == "__main__":
    main()
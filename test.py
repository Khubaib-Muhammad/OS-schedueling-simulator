import os
import random
import time
from scheduling_simulator import SchedulingSimulator, SchedulingAlgorithm, ProcessState

def test():
    sim = SchedulingSimulator()
    sim.memory_manager.reset(2048)
    sim.set_algorithm(SchedulingAlgorithm.ROUND_ROBIN)
    
    sim.add_process("P1", 0, 10, 1, False, 50)
    sim.add_process("P2", 2, 10, 1, False, 50)
    
    print("Starting simulation")
    sim.start_simulation()
    
    step = 0
    while sim.is_running:
        step += 1
        print(f"\nStep {step}")
        print(f"current_time: {sim.scheduler.current_time}")
        print(f"current_process: {sim.current_process.name if sim.current_process else 'None'}")
        print(f"P2 state: {sim.processes[1].state}")
        print(f"P2 arrival: {sim.processes[1].arrival_time}")
        print(f"ready_queue: {[p.name for p in sim.scheduler.ready_queue]}")
        
        ret = sim.step_simulation()
        print(f"step_simulation returned: {ret}")
        
        if step > 6:
            print("Stopping to analyze.")
            break

if __name__ == "__main__":
    test()

import unittest
import math
from scheduling_simulator import (
    SchedulingSimulator,
    Process,
    MemoryManager,
    PageReplacementAlgorithm,
    PageTableEntry
)

class TestVirtualMemory(unittest.TestCase):
    def setUp(self):
        self.sim = SchedulingSimulator()
        self.mem = self.sim.memory_manager
        self.mem.paging_enabled = True
        self.mem.page_size = 64
        self.mem.reset_paging()

    def test_paging_allocation(self):
        p1 = Process(
            pid=1,
            name="P1",
            arrival_time=0,
            burst_time=10,
            memory_required=100
        )
        self.sim.processes.append(p1)
        
        success = self.mem.allocate(p1)
        self.assertTrue(success)
        self.assertTrue(hasattr(p1, 'page_table'))
        self.assertEqual(len(p1.page_table), 2)
        
        # Verify demand warm-start: Page 0 should be present in a physical frame
        self.assertTrue(p1.page_table[0].is_present)
        self.assertIsNotNone(p1.page_table[0].frame_number)
        
        # Page 1 should start as not present
        self.assertFalse(p1.page_table[1].is_present)
        self.assertIsNone(p1.page_table[1].frame_number)

    def test_page_fault_counting(self):
        p1 = Process(
            pid=1,
            name="P1",
            arrival_time=0,
            burst_time=10,
            memory_required=100
        )
        self.sim.processes.append(p1)
        self.mem.allocate(p1)
        
        # Accessing Page 0 (present) should return True (no fault)
        success = self.mem.access_page(p1, 0, current_time=1.0)
        self.assertTrue(success)
        self.assertEqual(self.mem.page_faults.get(p1.pid, 0), 0)
        self.assertEqual(self.mem.total_page_faults, 0)
        
        # Accessing Page 1 (not present) should trigger a fault and return False
        success = self.mem.access_page(p1, 1, current_time=2.0)
        self.assertFalse(success)
        self.assertEqual(self.mem.page_faults.get(p1.pid, 0), 1)
        self.assertEqual(self.mem.total_page_faults, 1)
        
        # Now Page 1 should be loaded in RAM
        self.assertTrue(p1.page_table[1].is_present)

    def test_fifo_page_replacement(self):
        # Configure a small memory (128 MB) with 64 MB pages = exactly 2 physical frames
        self.mem.total_memory = 128
        self.mem.reset_paging()
        self.mem.replacement_algorithm = PageReplacementAlgorithm.FIFO
        
        p1 = Process(pid=1, name="P1", arrival_time=0, burst_time=10, memory_required=64)
        p2 = Process(pid=2, name="P2", arrival_time=0, burst_time=10, memory_required=64)
        p3 = Process(pid=3, name="P3", arrival_time=0, burst_time=10, memory_required=64)
        
        self.sim.processes.extend([p1, p2, p3])
        
        # Admitting P1 and P2 should completely fill the 2 frames
        self.mem.allocate(p1) # Frame 0 allocated to P1 Page 0
        self.mem.allocate(p2) # Frame 1 allocated to P2 Page 0
        
        self.assertTrue(p1.page_table[0].is_present)
        self.assertTrue(p2.page_table[0].is_present)
        self.assertEqual(self.mem.frames[0]['pid'], 1)
        self.assertEqual(self.mem.frames[1]['pid'], 2)
        
        # Now allocate P3 (requires 64 MB = 1 page)
        # Since physical memory is full, P1 Page 0 (the oldest loaded) should be evicted to swap space
        self.mem.allocate(p3)
        
        self.assertFalse(p1.page_table[0].is_present)
        self.assertIsNotNone(p1.page_table[0].swap_offset)
        self.assertTrue(p3.page_table[0].is_present)
        
        # Verify RAM layout: Frame 0 now contains P3 Page 0, Frame 1 contains P2 Page 0
        self.assertEqual(self.mem.frames[0]['pid'], 3)
        self.assertEqual(self.mem.frames[1]['pid'], 2)

    def test_lru_page_replacement(self):
        # Configure a small memory (128 MB) with 64 MB pages = exactly 2 physical frames
        self.mem.total_memory = 128
        self.mem.reset_paging()
        self.mem.replacement_algorithm = PageReplacementAlgorithm.LRU
        
        p1 = Process(pid=1, name="P1", arrival_time=0, burst_time=10, memory_required=64)
        p2 = Process(pid=2, name="P2", arrival_time=0, burst_time=10, memory_required=64)
        p3 = Process(pid=3, name="P3", arrival_time=0, burst_time=10, memory_required=64)
        
        self.sim.processes.extend([p1, p2, p3])
        
        # Allocate P1 and P2 to fill the frames
        self.mem.allocate(p1) # Loaded at t=0.0
        self.mem.allocate(p2) # Loaded at t=0.0
        
        # Update last accessed of P1 Page 0 at t=5.0
        self.mem.access_page(p1, 0, current_time=5.0)
        
        # At t=6.0, we allocate P3. Since Frame 1 (P2 Page 0, last accessed at t=0.0) is LRU,
        # it must be evicted instead of P1 Page 0 (last accessed at t=5.0)
        self.mem.allocate(p3)
        
        # Assertions: P1 Page 0 remains loaded, P2 Page 0 is evicted to swap
        self.assertTrue(p1.page_table[0].is_present)
        self.assertFalse(p2.page_table[0].is_present)
        self.assertIsNotNone(p2.page_table[0].swap_offset)
        self.assertTrue(p3.page_table[0].is_present)

    def test_paging_deallocation(self):
        p1 = Process(pid=1, name="P1", arrival_time=0, burst_time=10, memory_required=128)
        self.sim.processes.append(p1)
        
        self.mem.allocate(p1) # Loads Page 0 to Frame 0
        self.mem.load_page_into_ram(p1, 1, current_time=1.0) # Loads Page 1 to Frame 1
        
        # Evict Page 0 manually to swap space
        self.mem.evict_page(current_time=2.0)
        
        self.assertIsNotNone(p1.page_table[0].swap_offset)
        self.assertTrue(p1.page_table[1].is_present)
        
        # Now deallocate process
        self.mem.deallocate(p1.pid)
        
        # Assertions: all physical frames and swap elements cleared
        self.assertIsNone(self.mem.frames[0])
        self.assertIsNone(self.mem.frames[1])
        self.assertEqual(len(self.mem.swap_space), 0)

if __name__ == '__main__':
    unittest.main()

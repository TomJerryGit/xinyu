# -*- coding: utf-8 -*-
import threading, queue, time
from collections import OrderedDict
from logger import log

class AsyncQueue:
    def __init__(self, max_workers=3, max_results=100):
        self.task_queue = queue.Queue()
        self.results = OrderedDict()  # 使用有序字典，方便淘汰旧结果
        self.max_results = max_results  # 最多保留的结果数量
        self.running = True
        self._lock = threading.Lock()
        for _ in range(max_workers):
            t = threading.Thread(target=self._worker, daemon=True)
            t.start()
        log("info", f"异步队列启动 {max_workers} 线程")

    def _worker(self):
        while self.running:
            try:
                tid, func, args, kwargs = self.task_queue.get(timeout=1)
                try:
                    result = func(*args, **kwargs)
                    with self._lock:
                        self.results[tid] = {"status": "done", "result": result}
                        self._trim_results()
                except Exception as e:
                    with self._lock:
                        self.results[tid] = {"status": "error", "error": str(e)}
                        self._trim_results()
                self.task_queue.task_done()
            except queue.Empty:
                continue

    def _trim_results(self):
        """限制结果数量，删除最旧的已完成结果"""
        while len(self.results) > self.max_results:
            # 移除最早插入的键（OrderedDict 按插入顺序）
            oldest = next(iter(self.results))
            del self.results[oldest]

    def submit(self, tid, func, *args, **kwargs):
        with self._lock:
            self.results[tid] = {"status": "pending"}
        self.task_queue.put((tid, func, args, kwargs))

    def get_result(self, tid, timeout=30):
        start = time.time()
        while time.time() - start < timeout:
            with self._lock:
                if tid in self.results and self.results[tid]["status"] != "pending":
                    return self.results[tid]
            time.sleep(0.1)
        return {"status": "timeout", "error": "超时"}

    def shutdown(self):
        self.running = False
        # 等待所有队列任务完成（可选）
        # self.task_queue.join()
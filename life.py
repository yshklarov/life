#! /usr/bin/env python3

from enum import Enum, auto
import threading
import time
import tkinter as tk


WIDTH, HEIGHT = 501, 301


class Status(Enum):
    PAUSED = auto()
    PLAYING = auto()

class Cell(Enum):
    ALIVE = auto()
    DEAD = auto()

CELL_COLOR = {Cell.ALIVE: 'black',
              Cell.DEAD: 'white'}


class Stepper():
    """Run a specified function at regular time intervals.

    Begins in a paused state.
    """

    def __init__(self, interval=1, callback=None, *args, **kwargs):
        """Interval is in seconds. The callback does not need to be
        thread-safe. Optionally, args and kwargs are passed to the callback
        each time it is called."""
        self.callback = callback
        self.args = args
        self.kwargs = kwargs
        self.running = False
        self._interval = interval
        self._control_lock = threading.Lock()
        self._cb_lock = threading.Lock()
        self._timer = None

    def start(self):
        """Begin running the function at regular intervals."""
        with self._control_lock:
            if not self.running:
                self.running = True
                self._run()

    def stop(self):
        """Pause execution of the function."""
        with self._control_lock:
            self._stop()

    def set_interval(self, interval):
        """Set the interval between steps, in seconds."""
        with self._control_lock:
            if self.running and self._interval > 0.5:
                # Be responsive: Begin anew immediately (don't finish old
                # interval.)
                self._stop()
                self._interval = interval
                self.running = True
                self._run()
            else:
                self._interval = interval

    def _stop(self):
        self.running = False
        if self._timer:
            self._timer.cancel()

    def _run(self):
        # TODO Make the timing more accurate when interval is short, but still
        # never run the callback until the previous call has returned.
        with self._cb_lock:
            self.callback(*self.args, **self.kwargs)
        self._run_again()

    def _run_again(self):
        if self.running:
            self._timer = threading.Timer(self._interval, self._run)
            self._timer.start()


class World():
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.cells = self._fresh_cells()
        self.cells_changed = self._fresh_cells(state=False)

        # Glider
        self.cells[0][2] = Cell.ALIVE
        self.cells[1][2] = Cell.ALIVE
        self.cells[2][2] = Cell.ALIVE
        self.cells[2][1] = Cell.ALIVE
        self.cells[1][0] = Cell.ALIVE


    def flip_cell(self, x, y):
        if self.cells[y][x] == Cell.ALIVE:
            self.cells[y][x] = Cell.DEAD
        else:
            self.cells[y][x] = Cell.ALIVE
        self.cells_changed = self._fresh_cells(state=False)
        self.cells_changed[y][x] = True

    def step(self):
        next_cells = self._fresh_cells()
        next_cells_changed = self._fresh_cells(state=False)
        for x in range(0, self.width):
            for y in range(0, self.height):
                neighbors = [((x-1) % self.width, (y-1) % self.height),
                             ((x+0) % self.width, (y-1) % self.height),
                             ((x+1) % self.width, (y-1) % self.height),
                             ((x-1) % self.width, (y+0) % self.height),
                             ((x+1) % self.width, (y+0) % self.height),
                             ((x-1) % self.width, (y+1) % self.height),
                             ((x+0) % self.width, (y+1) % self.height),
                             ((x+1) % self.width, (y+1) % self.height)]
                living_neighbors = [self.cells[y][x] for x, y in neighbors].count(Cell.ALIVE)
                if living_neighbors == 3:
                    next_cells[y][x] = Cell.ALIVE
                elif living_neighbors == 2:
                    next_cells[y][x] = self.cells[y][x]
                next_cells_changed[y][x] = (self.cells[y][x] != next_cells[y][x])
        self.cells_changed = next_cells_changed
        self.cells = next_cells

    def _fresh_cells(self, state=Cell.DEAD):
        return [[Cell.DEAD for x in range(0, self.width)]
                for y in range(0, self.height)]


class Grid(tk.Canvas):
    def __init__(self, *args, height=HEIGHT, width=WIDTH, cell_height=10, cell_width=10, **kwargs):
        kwargs.setdefault('height', height)
        kwargs.setdefault('width', width)
        self.grid_size = (int((width-1) / cell_width),
                          int((height-1) / cell_height))
        self.usable_width = (self.grid_size[0] * cell_width) + 1
        self.usable_height = (self.grid_size[1] * cell_height) + 1
        self.cell_width = cell_width
        self.cell_height = cell_height
        super().__init__(*args, **kwargs)
        self.draw_grid()

    def draw_grid(self):
        for y in range(1, self.usable_height + 1, self.cell_height):
            self.create_line(1, y, self.usable_width+1, y, fill='#CCC')
        for x in range(1, self.usable_width + 1, self.cell_width):
            self.create_line(x, 1, x, self.usable_height+1, fill='#CCC')

    def fill_cell(self, x, y, color='black'):
        """The minimum value for x and y is 0. The maximum can be obtained
        from grid_size (a 2-tuple)."""
        if (not (0 <= x < self.grid_size[0]) or
            not (0 <= y < self.grid_size[1])):
            raise ValueError()
        left = x * self.cell_width + 2
        top = y * self.cell_height + 2
        right = left + self.cell_width - 1
        bottom = top + self.cell_height - 1
        self.create_rectangle(left, top, right, bottom, fill=color, outline='')

    def get_cell_coords_at(self, x, y):
        coord_x = (x-1) // self.cell_width
        coord_y = (y-1) // self.cell_height
        return (max(0, min(coord_x, self.grid_size[0]-1)),
                max(0, min(coord_y, self.grid_size[1]-1)))


class MainFrame(tk.Frame):
    def __init__(self, master=None):
        super().__init__(master)
        self.status = Status.PAUSED
        self.has_paused = False
        self.generation = 0
        self.pack()
        self.create_widgets()
        self.world = World(*self.grid.grid_size)
        self._paint_world()
        self.stepper = Stepper(callback=self.step)
        self.set_speed(self.speed_slider.get())

    def create_widgets(self):
        self.toolbar = tk.Frame(self)
        self.step_btn = tk.Button(self.toolbar, text='Step', command=self.step)
        self.step_btn.pack(side=tk.LEFT)
        self.play_pause_btn = tk.Button(self.toolbar, text='Play',
                                        command=self.play_pause)
        self.play_pause_btn.pack(side=tk.LEFT)
        self.speed_slider_lbl = tk.Label(self.toolbar, text="Speed:")
        self.speed_slider_lbl.pack(side=tk.LEFT)
        self.speed_slider = tk.Scale(self.toolbar, orient=tk.HORIZONTAL,
                                     from_=0, to=50, showvalue=0,
                                     command=self.set_speed)
        self.speed_slider.set(20)
        self.speed_slider.pack(side=tk.LEFT)
        self.gens_per_second_lbl = tk.Label(self.toolbar)
        self.gens_per_second_lbl.pack(side=tk.LEFT)
        self.generation_lbl_lbl = tk.Label(self.toolbar, text="Generations:")
        self.generation_lbl_lbl.pack(side=tk.LEFT)
        self.generation_lbl = tk.Label(self.toolbar, text='0', fg='dark green')
        self.generation_lbl.pack(side=tk.LEFT)
        self.toolbar.pack(side=tk.TOP)

        self.grid = Grid(self, width=WIDTH, height=HEIGHT, bd=0, bg='white')
        def _click_cb(event):
            x, y = self.grid.get_cell_coords_at(event.x, event.y)
            self.world.flip_cell(x, y)
            self._paint_world()
        self.grid.bind('<Button-1>', _click_cb)
        self.grid.pack(side=tk.BOTTOM)

    def step(self):
        self.generation += 1
        self.world.step()
        self._paint_world()
        self.generation_lbl['text'] = str(self.generation)

    def _paint_world(self):
        width, height = self.grid.grid_size
        for x in range(0, width):
            for y in range(0, height):
                if self.world.cells_changed[y][x]:
                    self.grid.fill_cell(x, y, CELL_COLOR[self.world.cells[y][x]])

    def play_pause(self):
        if self.status == Status.PAUSED:
            self.status = Status.PLAYING
            self.stepper.start()
            btn_text = 'Pause'
        elif self.status == Status.PLAYING:
            self.status = Status.PAUSED
            self.stepper.stop()
            self.has_paused = True
            btn_text = 'Play'
        self.play_pause_btn['text'] = btn_text

    def set_speed(self, speed_var):
        """Set the speed of the generation stepper. speed_var is a Tk variable
        or an integer."""
        gens_per_second = 1.1**int(speed_var)
        interval = 1 / gens_per_second
        if gens_per_second < 10:
            format_string = '{:.1f}'
        else:
            format_string = '{:.0f}'
        gens_per_second_str = format_string.format(gens_per_second)
        self.gens_per_second_lbl['text'] = gens_per_second_str
        self.stepper.set_interval(interval)

    def on_delete(self):
        # TODO Fix bug: Why does the thread not always join?
        self.stepper.stop()
        root.destroy()


if __name__ == '__main__':
    root = tk.Tk()
    frame = MainFrame()
    root.protocol("WM_DELETE_WINDOW", frame.on_delete)
    frame.master.title("Life")
    frame.mainloop()

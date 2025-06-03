import jack
import time
import datetime
import logging
import sys
from threading import Event
import numpy as np

log = logging.getLogger()

reconnect_wait_time = 2
reconnect_number_retries = 20


class TrackTracker:
    state_strings = {True: "playing", False: "stopped"}

    def __init__(self, track_id: int, threshold_time: float) -> None:
        self.is_playing = False
        self.timestamp_change = time.time()
        self.has_fired = False

        self.track_id = track_id
        self.threshold_time = threshold_time

    def update(self, new_playing_state):
        if new_playing_state == self.is_playing:
            if self.has_fired:
                return

            if self.timestamp_change + self.threshold_time <= time.time():
                self.has_fired = True
                change_time = datetime.datetime.fromtimestamp(self.timestamp_change)
                log.info(
                    f"[{change_time.isoformat()}] Track {self.track_id}: audio {self.state_strings[new_playing_state]}"
                )
        else:
            self.is_playing = new_playing_state
            self.timestamp_change = time.time()
            if new_playing_state == True:
                self.has_fired = True
                change_time = datetime.datetime.fromtimestamp(self.timestamp_change)
                log.info(
                    f"[{change_time.isoformat()}] Track {self.track_id}: audio {self.state_strings[new_playing_state]}"
                )
            else:
                self.has_fired = False


class SilenceDetector:

    def __init__(self, client_name: str, n_ports: int, threshold_time: float) -> None:
        self.stop_event = Event()
        self.n_ports = n_ports
        self.threshold_time = threshold_time

        self.silence_tracker = [TrackTracker(i, threshold_time) for i in range(n_ports)]
        self.setup_jack_client(client_name)

    def setup_jack_client(self, clientname, servername=None):
        n_tries = 0
        while n_tries < reconnect_number_retries:
            try:
                self.client = jack.Client(
                    clientname, no_start_server=True, servername=servername
                )
                break
            except jack.JackOpenError:
                logging.warn("couldn't connect to jack server. retrying...")
                n_tries += 1
                time.sleep(reconnect_wait_time)
        else:
            logging.error("could not connect to jack server")
            sys.exit(-2)

        @self.client.set_process_callback
        def process(frames):
            assert frames == self.client.blocksize
            for i, port in enumerate(self.client.inports):
                new_state = np.max(np.abs(port.get_array()))
                self.silence_tracker[i].update(not np.isclose(new_state, 0))
            # time.sleep(0.5)

        @self.client.set_xrun_callback
        def xrun(delayed_usecs: float):

            log.warning(
                f"[{datetime.datetime.now().isoformat()}] xrun happened: {delayed_usecs} usecs delayed"
            )

        for i in range(self.n_ports):
            self.client.inports.register((f"input_{i}"))

    def activate(self, *args):
        log.info("starting to listen")
        with self.client:
            self.stop_event.wait()

    def deactivate(self, *args):
        log.info("received deactivation signal")
        self.stop_event.set()

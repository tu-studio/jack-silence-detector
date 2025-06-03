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
    state_strings = {True: "started", False: "stopped"}

    def __init__(self, track_id: str, threshold_time: float) -> None:
        self.is_playing = False
        self.timestamp_change = time.time()
        self.has_fired = True

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
                    f"[{change_time.isoformat()}] {self.track_id}: audio {self.state_strings[new_playing_state]}"
                )
        else:
            self.is_playing = new_playing_state
            self.timestamp_change = time.time()
            if new_playing_state == True:
                self.has_fired = True
                change_time = datetime.datetime.fromtimestamp(self.timestamp_change)
                log.info(
                    f"[{change_time.isoformat()}] {self.track_id}: audio {self.state_strings[new_playing_state]}"
                )
            else:
                self.has_fired = False


class SilenceDetector:

    def __init__(
        self,
        client_name: str,
        listen_clients: tuple[str],
        n_ports: int,
        threshold_time: float,
    ) -> None:

        self.stop_event = Event()

        self.threshold_time = threshold_time
        self.listen_clients = listen_clients

        # setup for each port. if listen_clients exist set tracker ids to the names
        if len(listen_clients) > 0:
            self.n_ports = len(listen_clients)
            self.silence_tracker = [
                TrackTracker(cname, threshold_time) for cname in listen_clients
            ]
            self.connect_clients = True
        else:
            self.n_ports = n_ports
            self.silence_tracker = [
                TrackTracker(f"Track {i}", threshold_time) for i in range(n_ports)
            ]
            self.connect_clients = False

        self.setup_jack_client(client_name)

    def setup_jack_client(self, clientname, servername=None):
        # try to create the jack client
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

        # setup jack callbacks
        @self.client.set_process_callback
        def process(frames):
            assert frames == self.client.blocksize
            for i, port in enumerate(self.client.inports):
                # check if any
                new_state = np.max(np.abs(port.get_array()))
                self.silence_tracker[i].update(not np.isclose(new_state, 0))

        @self.client.set_xrun_callback
        def xrun(delayed_usecs: float):

            log.warning(
                f"[{datetime.datetime.now().isoformat()}] xrun happened: {delayed_usecs} usecs delayed"
            )

        # if listening clients should be connected register callback to register all relevant clients on connection
        if self.connect_clients:

            @self.client.set_port_registration_callback(only_available=True)
            def port_created(port: jack.Port, was_registered: bool):
                # skip irrelevant ports
                if not (port.is_audio and port.is_output and was_registered):
                    return

                # check if port belongs to one of the listen_clients
                for tracker, inport in zip(self.silence_tracker, self.client.inports):
                    if not np.any(
                        [
                            name.startswith(f"{tracker.track_id}:")
                            for name in [port.name] + port.aliases
                        ]
                    ):
                        continue
                    self.connect_port(port, inport)
                    break

        for i in range(self.n_ports):
            self.client.inports.register((f"input_{i}"))

    def connect_port(self, src: jack.Port, dest: jack.Port):
        if ":monitor" in src.name:
            return
        try:
            self.client.connect(src, dest)
        except jack.JackErrorCode as e:
            # handle connection already existing
            if e.code == 17:
                pass
            else:
                raise

    def activate(self, *args):
        """Activates the jack client, sets connection and starts blocking"""
        log.info("starting to listen")
        with self.client:

            # if necessary create connections
            if self.connect_clients:
                # iterate over client names
                for tracker, inport in zip(self.silence_tracker, self.client.inports):
                    listen_client_name = tracker.track_id

                    # get all outports belonging to this client
                    outports = self.client.get_ports(
                        f"{listen_client_name}:", is_audio=True, is_output=True
                    )

                    for outport in outports:
                        # skip monitor outputs in pipewire
                        self.connect_port(outport, inport)

            self.stop_event.wait()

    def deactivate(self, *args):
        log.info("received deactivation signal")
        self.stop_event.set()

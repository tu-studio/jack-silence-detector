import click
import logging
import signal

from jack_silence_detector.SilenceDetector import SilenceDetector


# logFormat = "%(asctime)s [%(levelname)-5.5s]: %(message)s"
logFormat = "%(message)s"
timeFormat = "%Y-%m-%d %H:%M:%S"
logging.basicConfig(format=logFormat, datefmt=timeFormat)
log = logging.getLogger()
log.setLevel(logging.INFO)


@click.command(
    help="Check for silences with jack client",
    context_settings=dict(help_option_names=["-h", "--help"]),
)
@click.option(
    "--client-name", help="Name for the jack client", default="jack_silence_detector"
)
@click.option(
    "-n",
    "--number-ports",
    help="Number of ports to open up for checking",
    default=1,
    type=click.IntRange(min=1, clamp=True),
)
@click.option(
    "-s",
    "--threshold-time",
    help="Time to wait before triggering on silence",
    default=1,
    type=(click.FloatRange(min=0, clamp=True)),
)
@click.version_option()
def main(client_name: str, number_ports: int, threshold_time: float):

    silence_detector = SilenceDetector(client_name, number_ports, threshold_time)

    for sig in [signal.SIGINT, signal.SIGTERM]:
        signal.signal(sig, silence_detector.deactivate)

    # start the connection loop
    silence_detector.activate()


if __name__ == "__main__":

    main()

from dataclasses import dataclass, field
import datetime


@dataclass
class RTCStats:
    """
    Base class for statistics.
    """

    timestamp: datetime.datetime = field(init=False)
    "The timestamp associated with this object."
    type: str = field()
    id: str = field()


@dataclass
class RTCRtpStreamStats(RTCStats):
    ssrc: int = field()
    kind: str = field()
    transportId: str = field()


@dataclass
class RTCReceivedRtpStreamStats(RTCRtpStreamStats):
    packetsReceived: int = field()
    packetsLost: int = field()
    jitter: int = field()


@dataclass
class RTCSentRtpStreamStats(RTCRtpStreamStats):
    packetsSent: int = field()
    "Total number of RTP packets sent for this SSRC."
    bytesSent: int = field()
    "Total number of bytes sent for this SSRC."


@dataclass
class RTCInboundRtpStreamStats(RTCReceivedRtpStreamStats):
    """
    The :class:`RTCInboundRtpStreamStats` dictionary represents the measurement
    metrics for the incoming RTP media stream.
    """


@dataclass
class RTCRemoteInboundRtpStreamStats(RTCReceivedRtpStreamStats):
    """
    The :class:`RTCRemoteInboundRtpStreamStats` dictionary represents the remote
    endpoint's measurement metrics for a particular incoming RTP stream.
    """

    roundTripTime: float = field()
    fractionLost: float = field()


@dataclass
class RTCOutboundRtpStreamStats(RTCSentRtpStreamStats):
    """
    The :class:`RTCOutboundRtpStreamStats` dictionary represents the measurement
    metrics for the outgoing RTP stream.
    """

    trackId: str = field()


@dataclass
class RTCRemoteOutboundRtpStreamStats(RTCSentRtpStreamStats):
    """
    The :class:`RTCRemoteOutboundRtpStreamStats` dictionary represents the remote
    endpoint's measurement metrics for its outgoing RTP stream.
    """

    remoteTimestamp: datetime.datetime = field(default=None)


@dataclass
class RTCTransportStats(RTCStats):
    packetsSent: int = field()
    "Total number of packets sent over this transport."
    packetsReceived: int = field()
    "Total number of packets received over this transport."
    bytesSent: int = field()
    "Total number of bytes sent over this transport."
    bytesReceived: int = field()
    "Total number of bytes received over this transport."
    iceRole: str = field()
    "The current value of :attr:`RTCIceTransport.role`."
    dtlsState: str = field()
    "The current value of :attr:`RTCDtlsTransport.state`."


class RTCStatsReport(dict):
    """
    Provides statistics data about WebRTC connections as returned by the
    :meth:`RTCPeerConnection.getStats()`, :meth:`RTCRtpReceiver.getStats()`
    and :meth:`RTCRtpSender.getStats()` coroutines.

    This object consists of a mapping of string identifiers to objects which
    are instances of:

    - :class:`RTCInboundRtpStreamStats`
    - :class:`RTCOutboundRtpStreamStats`
    - :class:`RTCRemoteInboundRtpStreamStats`
    - :class:`RTCRemoteOutboundRtpStreamStats`
    - :class:`RTCTransportStats`
    """

    def add(self, stats: RTCStats) -> None:
        self[stats.id] = stats

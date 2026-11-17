# Autoscaling policy

The API service scales out by one replica when average CPU utilisation exceeds 70% for five consecutive minutes. It scales in by one replica when utilisation stays below 30% for fifteen minutes. The minimum is 3 replicas and the maximum is 12. Scale-in is deliberately slower than scale-out to avoid flapping during bursty traffic.

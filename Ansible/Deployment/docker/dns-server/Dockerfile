FROM pihole/pihole:latest

EXPOSE 53/udp
EXPOSE 53/tcp
EXPOSE 80/tcp

ENV DNSMASQ_LISTENING=all

ARG PASSWORD
ENV FTLCONF_webserver_api_password=${PASSWORD}
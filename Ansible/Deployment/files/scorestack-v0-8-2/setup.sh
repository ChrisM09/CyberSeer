#!/bin/bash

# Install dependencies
yum install -y -q -e 0 epel-release
yum install -y -q -e 0 unzip openssl jq

# Generate certificate bundle if it isn't already generated
if [[ ! -f /certificates/bundle.zip ]]
then
  bin/elasticsearch-certutil cert --silent --pem --in config/instances.yml -out /certificates/bundle.zip
  unzip /certificates/bundle.zip -d /certificates
fi

# Set proper permissions on certificates directory
chown -R 1000:0 /certificates

# Wait for elasticsearch to come up
until curl -kX GET "${ELASTICSEARCH_HOST}/_cat/nodes?v&pretty"
do
  sleep 5
done

# Generate passwords
docker exec ${ELASTICSEARCH_CONTAINER} /bin/bash -c \
  "bin/elasticsearch-setup-passwords auto --batch \
  -Expack.security.http.ssl.key=/usr/share/elasticsearch/config/certificates/elasticsearch/elasticsearch.key \
  -Expack.security.http.ssl.certificate=/usr/share/elasticsearch/config/certificates/elasticsearch/elasticsearch.crt \
  -Expack.security.http.ssl.certificate_authorities=/usr/share/elasticsearch/config/certificates/ca/ca.crt \
  --url ${ELASTICSEARCH_HOST}" | grep PASSWORD > /tmp/cluster-passwords.txt

cat /tmp/cluster-passwords.txt


# Extract passwords from output
kibana_pass=$(cat /tmp/cluster-passwords.txt | grep 'kibana =' | awk '{print $NF}')
elastic_pass=$(cat /tmp/cluster-passwords.txt | grep elastic | awk '{print $NF}')
beats_pass=$(cat /tmp/cluster-passwords.txt | grep beats_system | awk '{print $NF}')

# Set passwords in kibana keystore
docker exec ${KIBANA_CONTAINER} bin/kibana-keystore create
docker exec ${KIBANA_CONTAINER} /bin/bash -c "bin/kibana-keystore add elasticsearch.password --stdin <<< '${kibana_pass}'"


# Restart kibana to reload credentials from keystore
docker restart kibana

# Write passwords to docker-compose default environment file
cat > config/.env << EOF
BEATS_PASSWORD=${beats_pass}
EOF

# Delete the passwords file
shred -uvz /tmp/cluster-passwords.txt

# Set Elastic admin password
curl -k -XPOST -u elastic:${elastic_pass} ${ELASTICSEARCH_HOST}/_security/user/elastic/_password -H "Content-Type: application/json" -d '{"password":"changeme"}'

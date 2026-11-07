# Secrets guide

If your application needs to store secrets, please read below for guidance.

## External Secrets Operator (ESO)

External Secrets Operator (ESO) syncs secrets from external secret managers (for example AWS Secrets Manager) into Kubernetes `Secret` objects. This keeps secret values out of Git and Helm values files. We use ESO in our clusters to manage secrets for applications.

### Small example

Here's a small example. Consider an application that needs 2 secrets, `clientId` and `clientSecret`. In AWS Secrets Manager, we create a new secret with name `com/sample-app/dev` with the following values:

```json
{
  "clientId": "foo123",
  "clientSecret": "bar789"
}
```

In the application helm chart, we create an `ExternalSecret` that maps these values to a Kubernetes secret, and the reconcilation of the secrets happens automatically every 7 days (168 hours):
```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: sample-app-secret                   # The name of your ExternalSecret
  namespace: default                        # Target application namespace
spec:
  refreshInterval: 168h                     # How often the operator reconciles the secret
  secretStoreRef:
    name: aws-secretsmanager                # The name of ClusterSecretStore (provided by SysOps team)
    kind: ClusterSecretStore
  target:
    name: my-new-secret                     # The name of the native k8s secret that will be created
    creationPolicy: Owner                   # The k8s secret is deleted if the ExternalSecret is deleted
  data:
    - secretKey: CLIENT_ID                  # The key name inside the generated k8s secret
      remoteRef:
        key: com/sample-app/dev     # The path to the secret in AWS Secrets Manager
        property: clientId                  # Specific field to extract from the above path
    - secretKey: CLIENT_SECRET
      remoteRef:
        key: com/sample-app/dev
        property: clientSecret
```

This creates/updates a Kubernetes secret named `my-new-secret` with keys `CLIENT_ID` and `CLIENT_SECRET`.

### Consuming the secret in your workloads

You can consume the generated Kubernetes secret as environment variables:

```yaml
# truncated version of deployment.yaml
      containers:
        - name: sample-app
          env:
            - name: CLIENT_ID
              valueFrom:
                secretKeyRef:
                  name: my-new-secret
                  key: CLIENT_ID
            - name: CLIENT_SECRET
              valueFrom:
                secretKeyRef:
                  name: my-new-secret
                  key: CLIENT_SECRET
```

Or mount it as files in a volume (preferred):

```yaml
# truncated version of deployment.yaml
      containers:
        - name: sample-app
          volumeMounts:
            - name: app-secrets-volume
              mountPath: /etc/secrets
              readOnly: true
      volumes:
        - name: app-secrets-volume
          secret:
            secretName: my-new-secret
```


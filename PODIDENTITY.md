# EKS Pod Identity guide

If your application needs access to AWS resources outside of the eks cluster, please follow for guidance.

## EKS Pod Identity

Amazon EKS Pod Identity is an AWS feature that lets Kubernetes workloads running in EKS access AWS services using IAM roles, without storing static AWS credentials in containers and without requiring the per-cluster OIDC provider setup used by IRSA. It is purpose-built for EKS and is intended to simplify how applications in a cluster get temporary AWS credentials for services such as S3, Secrets Manager, DynamoDB, and others.

### Small example

```yaml
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: my-app-sa   # This should match the service account name provided in pod-identity-association
  namespace: my-namespace
```

This creates/updates a Kubernetes service account resource `my-app-sa`. Keep in mind the service account should be in the same namespace as the application that is using it. Also one pod can mount only one service account. So all the permissions to all aws services need to be allowed in the role that maps to the service account.

### Using the service account in your workloads

You can use the Kubernetes service account by referencing it in your deployment manifest as follows:

```yaml
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
  namespace: my-namespace
spec:
  replicas: 1
  selector:
    matchLabels:
      app: my-app
  template:
    metadata:
      labels:
        app: my-app
    spec:
      serviceAccountName: my-app-sa
      containers:
        - name: my-app
          image: ......
```


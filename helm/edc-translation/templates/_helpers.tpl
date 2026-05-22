{{- define "edc-translation.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "edc-translation.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name (include "edc-translation.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "edc-translation.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "edc-translation.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{- define "edc-translation.selectorLabels" -}}
app.kubernetes.io/name: {{ include "edc-translation.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "edc-translation.componentSelectorLabels" -}}
{{ include "edc-translation.selectorLabels" .root }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "edc-translation.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
{{ include "edc-translation.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: edc-translation
{{- end -}}

{{- define "edc-translation.componentLabels" -}}
{{ include "edc-translation.labels" .root }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{/*
Local LLM env vars (for local_openai_compat provider) injected into containers
that perform live model calls (worker, mcp-http, main API).
*/}}
{{- define "edc-translation.localLlmEnv" -}}
{{- if .Values.localLlm.enabled }}
- name: EDC_TRANSLATION_LOCAL_LLM_BASE_URL
  value: {{ .Values.localLlm.baseUrl | quote }}
- name: EDC_TRANSLATION_LOCAL_LLM_MODEL_IDS
  value: {{ .Values.localLlm.modelIds | default "" | quote }}
{{- end }}
{{- end -}}

{{/*
Host access (hostAliases) injected into pod specs for pods that need to reach
host-bound services such as the external model at host.docker.internal:8081.
The hostIP must be a literal IP reachable from the pod to the host's port 8081.
*/}}
{{- define "edc-translation.hostAliases" -}}
{{- if and .Values.hostAccess.enabled .Values.hostAccess.hostIP }}
hostAliases:
  - ip: {{ .Values.hostAccess.hostIP | quote }}
    hostnames:
{{- range .Values.hostAccess.hostnames }}
      - {{ . | quote }}
{{- end }}
{{- end }}
{{- end -}}

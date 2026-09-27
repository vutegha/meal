import type {
  CollectionForm,
  FormInput,
  FormStatus,
  FormSummary,
  Submission,
  SubmissionInput,
} from "./api";
import { formExportPath } from "./api";
import { client, unwrap } from "./client";

/** Formulaires de collecte, par le client généré depuis l'OpenAPI. */

const at = (orgId: string, projectId: string) => ({ org_id: orgId, project_id: projectId });
const atForm = (orgId: string, projectId: string, formId: string) => ({
  ...at(orgId, projectId),
  form_id: formId,
});

const FORMS = "/api/v1/orgs/{org_id}/projects/{project_id}/forms";
const FORM = `${FORMS}/{form_id}` as const;

export const formsApi = {
  list: (orgId: string, projectId: string) =>
    unwrap(client.GET(FORMS, { params: { path: at(orgId, projectId) } })) as Promise<
      CollectionForm[]
    >,
  get: (orgId: string, projectId: string, formId: string) =>
    unwrap(
      client.GET(FORM, { params: { path: atForm(orgId, projectId, formId) } }),
    ) as Promise<CollectionForm>,
  create: (orgId: string, projectId: string, body: FormInput) =>
    unwrap(
      client.POST(FORMS, { params: { path: at(orgId, projectId) }, body }),
    ) as Promise<CollectionForm>,
  update: (
    orgId: string,
    projectId: string,
    formId: string,
    body: Partial<FormInput> & { status?: FormStatus },
  ) =>
    unwrap(
      client.PATCH(FORM, { params: { path: atForm(orgId, projectId, formId) }, body }),
    ) as Promise<CollectionForm>,
  remove: (orgId: string, projectId: string, formId: string) =>
    unwrap(client.DELETE(FORM, { params: { path: atForm(orgId, projectId, formId) } })).then(
      () => undefined,
    ),
  submit: (orgId: string, projectId: string, formId: string, body: SubmissionInput) =>
    unwrap(
      client.POST(`${FORM}/submissions`, {
        params: { path: atForm(orgId, projectId, formId) },
        body,
      }),
    ) as Promise<Submission>,
  submissions: (orgId: string, projectId: string, formId: string) =>
    unwrap(
      client.GET(`${FORM}/submissions`, { params: { path: atForm(orgId, projectId, formId) } }),
    ) as Promise<Submission[]>,
  removeSubmission: (orgId: string, projectId: string, formId: string, id: string) =>
    unwrap(
      client.DELETE(`${FORM}/submissions/{submission_id}`, {
        params: { path: { ...atForm(orgId, projectId, formId), submission_id: id } },
      }),
    ).then(() => undefined),
  summary: (orgId: string, projectId: string, formId: string) =>
    unwrap(
      client.GET(`${FORM}/summary`, { params: { path: atForm(orgId, projectId, formId) } }),
    ) as Promise<FormSummary>,
  exportPath: formExportPath,
};

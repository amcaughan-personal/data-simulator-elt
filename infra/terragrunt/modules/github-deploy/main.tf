# What GitHub Actions needs to deploy one environment's ingest code: a role that only that
# GitHub environment's jobs can assume, allowed to update and invoke this one function and
# nothing else, and the values the deploy workflow reads.
#
# The values are published to SSM at /github/<repo>/<environment>/<NAME>; personal-infra's
# GitHub stack turns each into a GitHub environment variable, read as vars.<NAME>.

data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [data.aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    # Only jobs in this GitHub environment (which allows only main) get these credentials.
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:amcaughan-personal/${var.github_repository}:environment:${var.github_environment}"]
    }
  }
}

data "aws_iam_policy_document" "deploy" {
  statement {
    sid       = "UpdateCode"
    actions   = ["lambda:UpdateFunctionCode", "lambda:GetFunction", "lambda:GetFunctionConfiguration"]
    resources = [var.function_arn]
  }
  # The smoke test runs the function once after each deploy.
  statement {
    sid       = "SmokeTest"
    actions   = ["lambda:InvokeFunction"]
    resources = [var.function_arn]
  }
}

resource "aws_iam_role" "deploy" {
  name                 = "${var.function_name}-deploy"
  description          = "GitHub Actions deploys of ${var.function_name} (environment ${var.github_environment})"
  assume_role_policy   = data.aws_iam_policy_document.assume.json
  max_session_duration = 3600
}

resource "aws_iam_role_policy" "deploy" {
  name   = "deploy-${var.function_name}"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.deploy.json
}

resource "aws_ssm_parameter" "variables" {
  #checkov:skip=CKV2_AWS_34:Not secrets: a role ARN and a function name, which workflow logs show anyway
  for_each = {
    DEPLOY_ROLE_ARN = aws_iam_role.deploy.arn
    FUNCTION_NAME   = var.function_name
  }

  name        = "/github/${var.github_repository}/${var.github_environment}/${each.key}"
  description = "GitHub environment variable ${each.key} for ${var.github_repository} (${var.github_environment})"
  type        = "String"
  value       = each.value
}

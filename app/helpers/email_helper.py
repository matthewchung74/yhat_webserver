from re import S
from app.helpers import boto_helper
from app.helpers.settings import settings
from pathlib import Path
import datetime

from app.db import schema
from app.helpers.boto_helper import create_presigned_url


async def send_build_email(
    user: schema.User,
    build: schema.Build,
    build_status: schema.BuildStatus,
):
    try:
        bucket = Path(build.build_log).parts[1]
        key = "/".join(list(Path(build.build_log).parts[2:]))
        build_log_url = create_presigned_url(bucket_name=bucket, object_name=key)

        sender = settings.SENDER_EMAIL
        status = ""
        if build_status == schema.BuildStatus.Finished:
            subject = f"Build all done for {build.notebook}"
            status = "Success"
        elif build_status == schema.BuildStatus.Error:
            subject = f"Build errored for {build.notebook}"
            status = "Error (Look in log for details)"
        else:
            subject = f"Build cancelled for {build.notebook}"
            status = "Cancelled"

        text: str = f"""
            Status: {status}\n
            Uploaded by: {user.github_username}\n
            Build: {build.id.split("-")[0]}\n
            Notebook: {build.get_github_url()}\n\n
            Build Log: {build_log_url}\n
            log link will be valid for 1 week
        """
        uploader_url = f"{settings.WEBSITE_URL}/profile/{user.id}"
        builder_url = f"{settings.WEBSITE_URL}/build_start/{build.id}"
        now = datetime.datetime.utcnow()
        now = now - datetime.timedelta(microseconds=now.microsecond)
        html: str = f"""
            Here are your build results for <a href='{build.get_github_url()}'>{build.notebook}</a> run on {now.isoformat()}<br>
            Status: {status}<br>
            Uploaded by: <a href='{uploader_url}'>{user.github_username}</a><br>
            Build: <a href='{builder_url}'>{build.id.split("-")[0]}</a><br>
            Build Log: <a href='{build_log_url}'>Download here</a><br>
            (log link will be valid for 1 week)
        """
        await boto_helper.send_email(
            to_address=user.email, sender=sender, subject=subject, text=text, html=html
        )
    except Exception as e:
        pass

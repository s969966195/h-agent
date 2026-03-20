"""
h_agent/skills/outlook - Windows Outlook Automation Skill

Provides automation for Microsoft Outlook:
- Mail: Send, receive, search, manage emails
- Calendar: Create, edit, delete appointments and meetings
- Contacts: Manage contacts and contact groups

Dependencies (Windows only):
    pip install pywin32

Usage:
    from h_agent.skills.outlook import Mail, Calendar, Contacts
    
    # Mail
    Mail.send_mail("recipient@example.com", "Subject", "Body")
    mails = Mail.search_emails("project update")
    
    # Calendar
    Calendar.create_appointment("Team Meeting", "10:00", "11:00", "Conference Room")
    
    # Contacts
    contact = Contacts.create_contact("John", "Doe", "john@example.com")
"""

import os
import sys
import platform
from pathlib import Path
from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timedelta

# Skill metadata
SKILL_NAME = "outlook"
SKILL_VERSION = "1.0.0"
SKILL_DESCRIPTION = "Windows Outlook automation (Mail, Calendar, Contacts)"
SKILL_AUTHOR = "h-agent team"
SKILL_CATEGORY = "office"
SKILL_DEPENDENCIES = ["win32com.client"]
SKILL_PLATFORMS = ["windows"]
SKILL_TOOLS = []
SKILL_FUNCTIONS = {}

# Check platform on import
if platform.system().lower() != "windows":
    def _windows_only():
        raise OSError("Outlook skill is only available on Windows")
    _windows_only_msg = _windows_only
else:
    _windows_only_msg = None


def _get_outlook_app():
    """Get Outlook COM object."""
    try:
        import win32com.client
        return win32com.client.Dispatch("Outlook.Application")
    except Exception as e:
        raise ImportError(
            f"Could not connect to Outlook: {e}\n"
            "Make sure Microsoft Outlook is installed."
        )


def _check_dependencies():
    """Check if required dependencies are installed."""
    missing = []
    for dep in SKILL_DEPENDENCIES:
        try:
            __import__(dep)
        except ImportError:
            missing.append(dep)
    if missing:
        raise ImportError(
            f"Missing dependencies for outlook skill: {', '.join(missing)}\n"
            f"Install with: pip install {' '.join(SKILL_DEPENDENCIES)}"
        )


# ─────────────────────────────────────────────
# Mail Operations
# ─────────────────────────────────────────────

class Mail:
    """Microsoft Outlook Mail automation."""
    
    @staticmethod
    def _get_namespace():
        """Get Outlook namespace."""
        outlook = _get_outlook_app()
        return outlook.GetNamespace("MAPI")
    
    @staticmethod
    def _get_inbox():
        """Get the default inbox folder."""
        ns = Mail._get_namespace()
        return ns.GetDefaultFolder(6)  # 6 = olFolderInbox
    
    @staticmethod
    def send_mail(to: str, subject: str, body: str, 
                  cc: Optional[str] = None, bcc: Optional[str] = None,
                  attachments: Optional[List[str]] = None,
                  html_body: bool = False) -> bool:
        """
        Send an email.
        
        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body content
            cc: CC recipient(s), comma-separated
            bcc: BCC recipient(s), comma-separated
            attachments: List of file paths to attach
            html_body: Whether body is HTML
            
        Returns:
            True if sent successfully
        """
        _check_dependencies()
        import win32com.client
        import pythoncom
        
        # Ensure COM is initialized
        pythoncom.CoInitialize()
        
        try:
            outlook = _get_outlook_app()
            mail = outlook.CreateItem(0)  # 0 = olMailItem
            
            mail.To = to
            mail.Subject = subject
            
            if html_body:
                mail.HTMLBody = body
            else:
                mail.Body = body
            
            if cc:
                mail.CC = cc
            if bcc:
                mail.BCC = bcc
            
            if attachments:
                for path in attachments:
                    if os.path.exists(path):
                        mail.Attachments.Add(path)
            
            mail.Send()
            return True
        except Exception as e:
            print(f"Failed to send mail: {e}")
            return False
        finally:
            pythoncom.CoUninitialize()
    
    @staticmethod
    def get_inbox(count: int = 10, unread_only: bool = False) -> List[Dict]:
        """
        Get recent emails from inbox.
        
        Args:
            count: Number of emails to retrieve
            unread_only: Only return unread emails
            
        Returns:
            List of email dictionaries
        """
        _check_dependencies()
        import pythoncom
        pythoncom.CoInitialize()
        
        try:
            inbox = Mail._get_inbox()
            items = inbox.Items
            items.Sort("[ReceivedTime]", True)  # Newest first
            
            emails = []
            for i, item in enumerate(items):
                if i >= count:
                    break
                if unread_only and item.UnRead == False:
                    continue
                
                emails.append({
                    "subject": item.Subject,
                    "sender": item.SenderEmailAddress,
                    "sender_name": item.SenderName,
                    "to": item.To,
                    "cc": item.CC,
                    "received_time": str(item.ReceivedTime),
                    "body": item.Body[:500] if item.Body else "",  # First 500 chars
                    "unread": item.UnRead,
                    "has_attachments": item.Attachments.Count > 0,
                    "entry_id": item.EntryID,
                })
            
            return emails
        finally:
            pythoncom.CoUninitialize()
    
    @staticmethod
    def search_emails(query: str, folder: Optional[str] = None, 
                      count: int = 50) -> List[Dict]:
        """
        Search emails using Outlook's built-in search.
        
        Args:
            query: Search query (e.g., "from:boss@example.com subject:report")
            folder: Folder to search in (default: inbox)
            count: Maximum results
            
        Returns:
            List of matching email dictionaries
        """
        _check_dependencies()
        import pythoncom
        pythoncom.CoInitialize()
        
        try:
            if folder:
                ns = Mail._get_namespace()
                inbox = ns.Folders[folder] if folder in [f.Name for f in ns.Folders] else Mail._get_inbox()
            else:
                inbox = Mail._get_inbox()
            
            items = inbox.Items
            items.Restrict(f"@SQL=\"{query}\"")
            
            results = []
            for i, item in enumerate(items):
                if i >= count:
                    break
                results.append({
                    "subject": item.Subject,
                    "sender": item.SenderEmailAddress,
                    "received_time": str(item.ReceivedTime),
                    "body": item.Body[:500] if item.Body else "",
                    "unread": item.UnRead,
                    "entry_id": item.EntryID,
                })
            
            return results
        except Exception as e:
            # Fallback to simple search
            return Mail._simple_search(query, count)
        finally:
            pythoncom.CoUninitialize()
    
    @staticmethod
    def _simple_search(query: str, count: int = 50) -> List[Dict]:
        """Simple keyword search in subject and body."""
        inbox = Mail._get_inbox()
        items = inbox.Items
        items.Sort("[ReceivedTime]", True)
        
        results = []
        query_lower = query.lower()
        for item in items:
            if len(results) >= count:
                break
            if (query_lower in item.Subject.lower()) or \
               (item.Body and query_lower in item.Body.lower()):
                results.append({
                    "subject": item.Subject,
                    "sender": item.SenderEmailAddress,
                    "received_time": str(item.ReceivedTime),
                    "body": item.Body[:500] if item.Body else "",
                    "unread": item.UnRead,
                    "entry_id": item.EntryID,
                })
        
        return results
    
    @staticmethod
    def mark_as_read(entry_id: str) -> bool:
        """Mark an email as read."""
        _check_dependencies()
        import pythoncom
        pythoncom.CoInitialize()
        
        try:
            ns = Mail._get_namespace()
            item = ns.GetItemFromID(entry_id)
            item.UnRead = False
            item.Save()
            return True
        except Exception as e:
            print(f"Failed to mark as read: {e}")
            return False
        finally:
            pythoncom.CoUninitialize()
    
    @staticmethod
    def mark_as_unread(entry_id: str) -> bool:
        """Mark an email as unread."""
        _check_dependencies()
        import pythoncom
        pythoncom.CoInitialize()
        
        try:
            ns = Mail._get_namespace()
            item = ns.GetItemFromID(entry_id)
            item.UnRead = True
            item.Save()
            return True
        except Exception as e:
            print(f"Failed to mark as unread: {e}")
            return False
        finally:
            pythoncom.CoUninitialize()
    
    @staticmethod
    def delete_email(entry_id: str) -> bool:
        """Delete an email (moves to Deleted Items)."""
        _check_dependencies()
        import pythoncom
        pythoncom.CoInitialize()
        
        try:
            ns = Mail._get_namespace()
            item = ns.GetItemFromID(entry_id)
            item.Delete()
            return True
        except Exception as e:
            print(f"Failed to delete email: {e}")
            return False
        finally:
            pythoncom.CoUninitialize()
    
    @staticmethod
    def get_attachment(entry_id: str, attachment_index: int = 0, 
                       save_path: Optional[str] = None) -> Optional[str]:
        """
        Save an attachment from an email.
        
        Args:
            entry_id: Email entry ID
            attachment_index: Index of attachment (0-based)
            save_path: Path to save to (default: current directory)
            
        Returns:
            Path where attachment was saved
        """
        _check_dependencies()
        import pythoncom
        pythoncom.CoInitialize()
        
        try:
            ns = Mail._get_namespace()
            item = ns.GetItemFromID(entry_id)
            
            if attachment_index >= item.Attachments.Count:
                return None
            
            attachment = item.Attachments[attachment_index + 1]  # 1-based
            filename = attachment.FileName
            
            if not save_path:
                save_path = os.path.join(os.getcwd(), filename)
            
            attachment.SaveAsFile(save_path)
            return save_path
        except Exception as e:
            print(f"Failed to save attachment: {e}")
            return None
        finally:
            pythoncom.CoUninitialize()


# ─────────────────────────────────────────────
# Calendar Operations
# ─────────────────────────────────────────────

class Calendar:
    """Microsoft Outlook Calendar automation."""
    
    @staticmethod
    def _get_calendar():
        """Get the default calendar folder."""
        import win32com.client
        outlook = _get_outlook_app()
        ns = outlook.GetNamespace("MAPI")
        return ns.GetDefaultFolder(9)  # 9 = olFolderCalendar
    
    @staticmethod
    def create_appointment(subject: str, start_time: Union[str, datetime],
                          end_time: Union[str, datetime],
                          location: Optional[str] = None,
                          body: Optional[str] = None,
                          reminder: Optional[int] = 15,
                          all_day: bool = False,
                          categories: Optional[List[str]] = None) -> Optional[str]:
        """
        Create a calendar appointment.
        
        Args:
            subject: Appointment title
            start_time: Start time (datetime object or "YYYY-MM-DD HH:MM" string)
            end_time: End time (datetime object or "YYYY-MM-DD HH:MM" string)
            location: Location string
            body: Appointment body/notes
            reminder: Reminder minutes before (None to disable)
            all_day: Whether this is an all-day event
            categories: List of category names
            
        Returns:
            Entry ID of created appointment
        """
        _check_dependencies()
        import win32com.client
        import pythoncom
        pythoncom.CoInitialize()
        
        try:
            outlook = _get_outlook_app()
            appt = outlook.CreateItem(1)  # 1 = olAppointmentItem
            
            # Parse times
            if isinstance(start_time, str):
                start_time = datetime.strptime(start_time, "%Y-%m-%d %H:%M")
            if isinstance(end_time, str):
                end_time = datetime.strptime(end_time, "%Y-%m-%d %H:%M")
            
            appt.Subject = subject
            appt.Start = start_time
            appt.End = end_time
            appt.AllDayEvent = all_day
            
            if location:
                appt.Location = location
            if body:
                appt.Body = body
            if reminder is not None:
                appt.ReminderSet = True
                appt.ReminderMinutesBeforeStart = reminder
            else:
                appt.ReminderSet = False
            
            if categories:
                appt.Categories = "; ".join(categories)
            
            appt.Save()
            return appt.EntryID
        except Exception as e:
            print(f"Failed to create appointment: {e}")
            return None
        finally:
            pythoncom.CoUninitialize()
    
    @staticmethod
    def get_appointments(start_date: Optional[datetime] = None,
                         end_date: Optional[datetime] = None,
                         count: int = 50) -> List[Dict]:
        """
        Get calendar appointments.
        
        Args:
            start_date: Start of date range (default: today)
            end_date: End of date range (default: 7 days from today)
            count: Maximum number of appointments
            
        Returns:
            List of appointment dictionaries
        """
        _check_dependencies()
        import pythoncom
        pythoncom.CoInitialize()
        
        try:
            calendar = Calendar._get_calendar()
            items = calendar.Items
            items.Sort("[Start]")
            items.IncludeRecurrences = True
            
            if not start_date:
                start_date = datetime.now().replace(hour=0, minute=0, second=0)
            if not end_date:
                end_date = start_date + timedelta(days=7)
            
            # Filter by date range
            restriction = f"[Start] >= '{start_date.strftime('%m/%d/%Y')}' AND [End] <= '{end_date.strftime('%m/%d/%Y 23:59')}'"
            filtered = items.Restrict(restriction)
            
            appointments = []
            for i, appt in enumerate(filtered):
                if i >= count:
                    break
                appointments.append({
                    "subject": appt.Subject,
                    "start": str(appt.Start),
                    "end": str(appt.End),
                    "location": appt.Location,
                    "body": appt.Body[:500] if appt.Body else "",
                    "all_day": appt.AllDayEvent,
                    "reminder": appt.ReminderMinutesBeforeStart if appt.ReminderSet else None,
                    "categories": appt.Categories,
                    "busy": appt.BusyStatus,
                    "entry_id": appt.EntryID,
                })
            
            return appointments
        finally:
            pythoncom.CoUninitialize()
    
    @staticmethod
    def get_today_appointments() -> List[Dict]:
        """Get today's appointments."""
        today = datetime.now().replace(hour=0, minute=0, second=0)
        tomorrow = today + timedelta(days=1)
        return Calendar.get_appointments(today, tomorrow)
    
    @staticmethod
    def get_upcoming_appointments(days: int = 7) -> List[Dict]:
        """Get upcoming appointments for the next N days."""
        start_date = datetime.now()
        end_date = start_date + timedelta(days=days)
        return Calendar.get_appointments(start_date, end_date)
    
    @staticmethod
    def update_appointment(entry_id: str, **kwargs) -> bool:
        """
        Update an appointment.
        
        Args:
            entry_id: Appointment entry ID
            **kwargs: Fields to update (subject, start, end, location, body, etc.)
            
        Returns:
            True if successful
        """
        _check_dependencies()
        import pythoncom
        pythoncom.CoInitialize()
        
        try:
            ns = Calendar._get_namespace().Parent  # Get parent namespace
            outlook = _get_outlook_app()
            appt = outlook.GetItemFromID(entry_id)
            
            for key, value in kwargs.items():
                if hasattr(appt, key):
                    if key == "start" and isinstance(value, str):
                        value = datetime.strptime(value, "%Y-%m-%d %H:%M")
                    elif key == "end" and isinstance(value, str):
                        value = datetime.strptime(value, "%Y-%m-%d %H:%M")
                    setattr(appt, key, value)
            
            appt.Save()
            return True
        except Exception as e:
            print(f"Failed to update appointment: {e}")
            return False
        finally:
            pythoncom.CoUninitialize()
    
    @staticmethod
    def delete_appointment(entry_id: str) -> bool:
        """Delete an appointment."""
        _check_dependencies()
        import pythoncom
        pythoncom.CoInitialize()
        
        try:
            outlook = _get_outlook_app()
            appt = outlook.GetItemFromID(entry_id)
            appt.Delete()
            return True
        except Exception as e:
            print(f"Failed to delete appointment: {e}")
            return False
        finally:
            pythoncom.CoUninitialize()
    
    @staticmethod
    def create_meeting(subject: str, start_time: Union[str, datetime],
                       end_time: Union[str, datetime],
                       attendees: List[str],
                       location: Optional[str] = None,
                       body: Optional[str] = None,
                       reminder: int = 15) -> Optional[str]:
        """
        Create a meeting with attendees.
        
        Args:
            subject: Meeting title
            start_time: Start time
            end_time: End time
            attendees: List of email addresses
            location: Meeting location
            body: Meeting notes
            reminder: Reminder minutes before
            
        Returns:
            Entry ID of created meeting
        """
        _check_dependencies()
        import pythoncom
        pythoncom.CoInitialize()
        
        try:
            outlook = _get_outlook_app()
            meeting = outlook.CreateItem(1)  # olAppointmentItem
            meeting.MeetingStatus = 1  # olMeeting
            
            if isinstance(start_time, str):
                start_time = datetime.strptime(start_time, "%Y-%m-%d %H:%M")
            if isinstance(end_time, str):
                end_time = datetime.strptime(end_time, "%Y-%m-%d %H:%M")
            
            meeting.Subject = subject
            meeting.Start = start_time
            meeting.End = end_time
            meeting.Location = location or ""
            meeting.Body = body or ""
            meeting.ReminderMinutesBeforeStart = reminder
            meeting.ReminderSet = True
            
            # Add attendees
            meeting.Recipients.Add(attendees[0])
            for attendee in attendees[1:]:
                meeting.Recipients.Add(attendee)
            
            meeting.Send()
            return meeting.EntryID
        except Exception as e:
            print(f"Failed to create meeting: {e}")
            return None
        finally:
            pythoncom.CoUninitialize()


# ─────────────────────────────────────────────
# Contacts Operations
# ─────────────────────────────────────────────

class Contacts:
    """Microsoft Outlook Contacts automation."""
    
    @staticmethod
    def _get_contacts_folder():
        """Get the default contacts folder."""
        outlook = _get_outlook_app()
        ns = outlook.GetNamespace("MAPI")
        return ns.GetDefaultFolder(10)  # 10 = olFolderContacts
    
    @staticmethod
    def create_contact(first_name: str, last_name: str, 
                       email: Optional[str] = None,
                       phone: Optional[str] = None,
                       mobile: Optional[str] = None,
                       company: Optional[str] = None,
                       title: Optional[str] = None,
                       address: Optional[str] = None,
                       notes: Optional[str] = None) -> Optional[str]:
        """
        Create a new contact.
        
        Args:
            first_name: First name
            last_name: Last name
            email: Email address
            phone: Business phone
            mobile: Mobile phone
            company: Company name
            title: Job title
            address: Street address
            notes: Additional notes
            
        Returns:
            Entry ID of created contact
        """
        _check_dependencies()
        import pythoncom
        pythoncom.CoInitialize()
        
        try:
            outlook = _get_outlook_app()
            contact = outlook.CreateItem(2)  # 2 = olContactItem
            
            contact.FirstName = first_name
            contact.LastName = last_name
            
            if email:
                contact.Email1Address = email
            if phone:
                contact.BusinessTelephoneNumber = phone
            if mobile:
                contact.MobileTelephoneNumber = mobile
            if company:
                contact.CompanyName = company
            if title:
                contact.JobTitle = title
            if address:
                contact.BusinessAddress = address
            if notes:
                contact.Body = notes
            
            contact.Save()
            return contact.EntryID
        except Exception as e:
            print(f"Failed to create contact: {e}")
            return None
        finally:
            pythoncom.CoUninitialize()
    
    @staticmethod
    def search_contacts(query: str, count: int = 50) -> List[Dict]:
        """
        Search contacts by name or email.
        
        Args:
            query: Search query
            count: Maximum results
            
        Returns:
            List of contact dictionaries
        """
        _check_dependencies()
        import pythoncom
        pythoncom.CoInitialize()
        
        try:
            folder = Contacts._get_contacts_folder()
            items = folder.Items
            
            results = []
            query_lower = query.lower()
            
            for i, contact in enumerate(items):
                if i >= count * 2:  # Check more to filter
                    break
                
                name = f"{contact.FirstName or ''} {contact.LastName or ''}".lower()
                email = (contact.Email1Address or "").lower()
                
                if query_lower in name or query_lower in email:
                    results.append({
                        "name": f"{contact.FirstName} {contact.LastName}".strip(),
                        "first_name": contact.FirstName,
                        "last_name": contact.LastName,
                        "email": contact.Email1Address,
                        "phone": contact.BusinessTelephoneNumber,
                        "mobile": contact.MobileTelephoneNumber,
                        "company": contact.CompanyName,
                        "title": contact.JobTitle,
                        "entry_id": contact.EntryID,
                    })
                    
                    if len(results) >= count:
                        break
            
            return results
        finally:
            pythoncom.CoUninitialize()
    
    @staticmethod
    def get_contact(entry_id: str) -> Optional[Dict]:
        """
        Get a contact by entry ID.
        
        Args:
            entry_id: Contact entry ID
            
        Returns:
            Contact dictionary
        """
        _check_dependencies()
        import pythoncom
        pythoncom.CoInitialize()
        
        try:
            outlook = _get_outlook_app()
            contact = outlook.GetItemFromID(entry_id)
            
            return {
                "name": f"{contact.FirstName} {contact.LastName}".strip(),
                "first_name": contact.FirstName,
                "last_name": contact.LastName,
                "email": contact.Email1Address,
                "phone": contact.BusinessTelephoneNumber,
                "mobile": contact.MobileTelephoneNumber,
                "company": contact.CompanyName,
                "title": contact.JobTitle,
                "address": contact.BusinessAddress,
                "notes": contact.Body,
                "entry_id": contact.EntryID,
            }
        except Exception as e:
            print(f"Failed to get contact: {e}")
            return None
        finally:
            pythoncom.CoUninitialize()
    
    @staticmethod
    def update_contact(entry_id: str, **kwargs) -> bool:
        """
        Update a contact.
        
        Args:
            entry_id: Contact entry ID
            **kwargs: Fields to update
            
        Returns:
            True if successful
        """
        _check_dependencies()
        import pythoncom
        pythoncom.CoInitialize()
        
        try:
            outlook = _get_outlook_app()
            contact = outlook.GetItemFromID(entry_id)
            
            for key, value in kwargs.items():
                if hasattr(contact, key):
                    setattr(contact, key, value)
            
            contact.Save()
            return True
        except Exception as e:
            print(f"Failed to update contact: {e}")
            return False
        finally:
            pythoncom.CoUninitialize()
    
    @staticmethod
    def delete_contact(entry_id: str) -> bool:
        """Delete a contact."""
        _check_dependencies()
        import pythoncom
        pythoncom.CoUninitialize()
        
        try:
            outlook = _get_outlook_app()
            contact = outlook.GetItemFromID(entry_id)
            contact.Delete()
            return True
        except Exception as e:
            print(f"Failed to delete contact: {e}")
            return False
        finally:
            pythoncom.CoUninitialize()
    
    @staticmethod
    def create_distribution_list(name: str, members: List[str]) -> Optional[str]:
        """
        Create a distribution list (contact group).
        
        Args:
            name: List name
            members: List of email addresses
            
        Returns:
            Entry ID of created list
        """
        _check_dependencies()
        import pythoncom
        pythoncom.CoInitialize()
        
        try:
            outlook = _get_outlook_app()
            dl = outlook.CreateItem(7)  # olDistributionListItem
            dl.DLName = name
            
            for email in members:
                dl.AddMember(email)
            
            dl.Save()
            return dl.EntryID
        except Exception as e:
            print(f"Failed to create distribution list: {e}")
            return None
        finally:
            pythoncom.CoUninitialize()


# ─────────────────────────────────────────────
# Register skill functions
# ─────────────────────────────────────────────

SKILL_FUNCTIONS = {
    # Mail
    "mail_send": Mail.send_mail,
    "mail_get_inbox": Mail.get_inbox,
    "mail_search": Mail.search_emails,
    "mail_mark_read": Mail.mark_as_read,
    "mail_mark_unread": Mail.mark_as_unread,
    "mail_delete": Mail.delete_email,
    "mail_get_attachment": Mail.get_attachment,
    
    # Calendar
    "calendar_create_appointment": Calendar.create_appointment,
    "calendar_get_appointments": Calendar.get_appointments,
    "calendar_get_today": Calendar.get_today_appointments,
    "calendar_get_upcoming": Calendar.get_upcoming_appointments,
    "calendar_update": Calendar.update_appointment,
    "calendar_delete": Calendar.delete_appointment,
    "calendar_create_meeting": Calendar.create_meeting,
    
    # Contacts
    "contacts_create": Contacts.create_contact,
    "contacts_search": Contacts.search_contacts,
    "contacts_get": Contacts.get_contact,
    "contacts_update": Contacts.update_contact,
    "contacts_delete": Contacts.delete_contact,
    "contacts_create_distribution_list": Contacts.create_distribution_list,
}

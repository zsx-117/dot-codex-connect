"""Classify observed server requests without answering or approving them."""
APPROVAL = {'item/commandExecution/requestApproval', 'item/fileChange/requestApproval',
            'item/permissions/requestApproval'}
INPUT = {'item/tool/requestUserInput', 'tool/requestUserInput', 'mcpServer/elicitation/request'}


def request_interaction(method):
    if method in APPROVAL:
        return {'kind': 'approval', 'pendingState': 'awaiting_approval', 'method': method}
    if method in INPUT:
        return {'kind': 'input', 'pendingState': 'needs_input', 'method': method}
    return {'kind': 'desktop_tool' if method == 'item/tool/call' else 'unsupported_request',
            'pendingState': 'needs_desktop',
            'method': method if method == 'item/tool/call' else 'unsupported_server_request'}

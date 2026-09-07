#pragma once

#include <QMainWindow>
#include <QJsonObject>

#include "api_client.h"

class QDragEnterEvent;
class QDropEvent;
class QEvent;
class QLabel;
class QListWidget;
class QListWidgetItem;
class QPlainTextEdit;
class QPushButton;
class QStackedWidget;
class QTextEdit;
class QTimer;
class QWidget;

class MainWindow final : public QMainWindow
{
    Q_OBJECT

public:
    explicit MainWindow(
        const QString &username,
        const QString &accessToken,
        QWidget *parent = nullptr);

protected:
    bool eventFilter(QObject *watched, QEvent *event) override;
    void dragEnterEvent(QDragEnterEvent *event) override;
    void dropEvent(QDropEvent *event) override;

signals:
    void logoutRequested();

private:
    ApiClient m_api;
    QString m_username;

    QListWidget *m_agentList = nullptr;
    QTextEdit *m_chatDisplay = nullptr;
    QPlainTextEdit *m_inputArea = nullptr;
    QPushButton *m_sendButton = nullptr;
    QLabel *m_targetLabel = nullptr;
    QLabel *m_connectionLabel = nullptr;
    QLabel *m_dropHint = nullptr;
    QTimer *m_requestTimeout = nullptr;

    QString m_currentTarget = "Handler";
    bool m_requestBusy = false;

    QWidget *buildSidebar();
    QWidget *buildChatArea();
    QWidget *buildTopBar();
    QWidget *buildComposer();

    void applyWindowStyle();
    void openSettings();
    void sendCurrentMessage();
    void selectTarget(QListWidgetItem *item);
    void updateAgents(const QJsonObject &json);
    void setBusy(bool busy);
    void addMessage(
        const QString &sender,
        const QString &message,
        bool userMessage,
        bool errorMessage = false);
    void addSystemMessage(const QString &message);
    void handleResponse(const QString &title, const QJsonObject &json);
    void handleError(const QString &message);
    [[nodiscard]] QString responseText(
        const QString &title,
        const QJsonObject &json) const;
};
